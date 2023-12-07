from __future__ import annotations

import copy
import inspect
import os
import string
import sys
import warnings
from functools import partial
from itertools import chain
from time import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Type, Union

import logging
from viur.core import conf, current, db, email, errors, translate, utils
from viur.core.bones import BaseBone, DateBone, KeyBone, RelationalBone, RelationalUpdateLevel, SelectBone, StringBone
from viur.core.bones.base import Compute, ComputeInterval, ComputeMethod, ReadFromClientError, \
    ReadFromClientErrorSeverity, getSystemInitialized
from viur.core.tasks import CallDeferred, CallableTask, CallableTaskBase, QueryIter

_undefined = object()


class MetaBaseSkel(type):
    """
        This is the metaclass for Skeletons.
        It is used to enforce several restrictions on bone names, etc.
    """
    _skelCache = {}  # Mapping kindName -> SkelCls
    _allSkelClasses = set()  # list of all known skeleton classes (including Ref and Mail-Skels)

    # List of reserved keywords and function names
    __reserved_keywords = {
        "all",
        "bounce",
        "clone",
        "cursor",
        "delete",
        "fromClient",
        "fromDB",
        "get",
        "getCurrentSEOKeys",
        "items",
        "keys",
        "limit",
        "orderby",
        "orderdir",
        "postDeletedHandler",
        "postSavedHandler",
        "preProcessBlobLocks",
        "preProcessSerializedData",
        "refresh",
        "self",
        "serialize",
        "setBoneValue",
        "style",
        "structure",
        "toDB",
        "unserialize",
        "values",
    }

    __allowed_chars = string.ascii_letters + string.digits + "_"

    def __init__(cls, name, bases, dct):
        cls.__boneMap__ = MetaBaseSkel.generate_bonemap(cls)

        if not getSystemInitialized():
            MetaBaseSkel._allSkelClasses.add(cls)

        super(MetaBaseSkel, cls).__init__(name, bases, dct)

    @staticmethod
    def generate_bonemap(cls):
        """
        Recursively constructs a dict of bones from
        """
        map = {}

        for base in cls.__bases__:
            if "__viurBaseSkeletonMarker__" in dir(base):
                map |= MetaBaseSkel.generate_bonemap(base)

        for key in cls.__dict__:
            prop = getattr(cls, key)

            if isinstance(prop, BaseBone):
                if not all([c in MetaBaseSkel.__allowed_chars for c in key]):
                    raise AttributeError(f"Invalid bone name: {key!r} contains invalid characters")
                elif key in MetaBaseSkel.__reserved_keywords:
                    raise AttributeError(f"Invalid bone name: {key!r} is reserved and cannot be used")

                map[key] = prop

            elif prop is None and key in map:  # Allow removing a bone in a subclass by setting it to None
                del map[key]

        return map


def skeletonByKind(kindName: str) -> Type[Skeleton]:
    """
        Returns the Skeleton-Class for the given kindName. That skeleton must exist, otherwise an exception is raised.
        :param kindName: The kindname to retreive the skeleton for
        :return: The skeleton-class for that kind
    """
    assert kindName in MetaBaseSkel._skelCache, "Unknown skeleton '%s'" % kindName
    return MetaBaseSkel._skelCache[kindName]


def listKnownSkeletons() -> List[str]:
    """
        :return: A list of all known kindnames (all kindnames for which a skeleton is defined)
    """
    return list(MetaBaseSkel._skelCache.keys())[:]


def iterAllSkelClasses() -> Iterable["Skeleton"]:
    """
        :return: An iterator that yields each Skeleton-Class once. (Only top-level skeletons are returned, so no
            RefSkel classes will be included)
    """
    for cls in list(MetaBaseSkel._allSkelClasses):  # We'll add new classes here during setSystemInitialized()
        yield cls


class SkeletonInstance:
    """
        The actual wrapper around a Skeleton-Class. An object of this class is what's actually returned when you
        call a Skeleton-Class. With ViUR3, you don't get an instance of a Skeleton-Class any more - it's always this
        class. This is much faster as this is a small class.
    """
    __slots__ = {"dbEntity", "accessedValues", "renderAccessedValues", "boneMap", "errors", "skeletonCls",
                 "renderPreparation"}

    def __init__(self, skelCls, subSkelNames=None, fullClone=False, clonedBoneMap=None):
        if clonedBoneMap:
            self.boneMap = clonedBoneMap
        elif subSkelNames:
            boneList = ["key"] + list(chain(*[skelCls.subSkels.get(x, []) for x in ["*"] + subSkelNames]))
            doesMatch = lambda name: name in boneList or any(
                [name.startswith(x[:-1]) for x in boneList if x[-1] == "*"])
            if fullClone:
                self.boneMap = {k: copy.deepcopy(v) for k, v in skelCls.__boneMap__.items() if doesMatch(k)}
                for v in self.boneMap.values():
                    v.isClonedInstance = True
            else:
                self.boneMap = {k: v for k, v in skelCls.__boneMap__.items() if doesMatch(k)}
        elif fullClone:
            self.boneMap = copy.deepcopy(skelCls.__boneMap__)
            for v in self.boneMap.values():
                v.isClonedInstance = True
        else:  # No Subskel, no Clone
            self.boneMap = skelCls.__boneMap__.copy()
        self.dbEntity = None
        self.accessedValues = {}
        self.renderAccessedValues = {}
        self.errors = []
        self.skeletonCls = skelCls
        self.renderPreparation = None

    def items(self, yieldBoneValues: bool = False) -> Iterable[Tuple[str, BaseBone]]:
        if yieldBoneValues:
            for key in self.boneMap.keys():
                yield key, self[key]
        else:
            yield from self.boneMap.items()

    def keys(self) -> Iterable[str]:
        yield from self.boneMap.keys()

    def values(self) -> Iterable[Any]:
        yield from self.boneMap.values()

    def __iter__(self) -> Iterable[str]:
        yield from self.keys()

    def __contains__(self, item):
        return item in self.boneMap

    def get(self, item, default=None):
        if item not in self:
            return default

        return self[item]

    def __setitem__(self, key, value):
        assert self.renderPreparation is None, "Cannot modify values while rendering"
        if isinstance(value, BaseBone):
            raise AttributeError("Don't assign this bone object as skel[\"%s\"] = ... anymore to the skeleton. "
                                 "Use skel.%s = ... for bone to skeleton assignment!" % (key, key))
        self.accessedValues[key] = value

    def __getitem__(self, key):
        if self.renderPreparation:
            if key in self.renderAccessedValues:
                return self.renderAccessedValues[key]
        if key not in self.accessedValues:
            boneInstance = self.boneMap.get(key, None)
            if boneInstance:
                if self.dbEntity is not None:
                    boneInstance.unserialize(self, key)
                else:
                    self.accessedValues[key] = boneInstance.getDefaultValue(self)
        if not self.renderPreparation:
            return self.accessedValues.get(key)
        value = self.renderPreparation(getattr(self, key), self, key, self.accessedValues.get(key))
        self.renderAccessedValues[key] = value
        return value

    def __getattr__(self, item):
        if item == "boneMap":
            return {}  # There are __setAttr__ calls before __init__ has run
        elif item in {"kindName", "interBoneValidations", "customDatabaseAdapter"}:
            return getattr(self.skeletonCls, item)
        elif item in {"fromDB", "toDB", "all", "unserialize", "serialize", "fromClient", "getCurrentSEOKeys",
                      "preProcessSerializedData", "preProcessBlobLocks", "postSavedHandler", "setBoneValue",
                      "delete", "postDeletedHandler", "refresh"}:
            return partial(getattr(self.skeletonCls, item), self)
        try:
            return self.boneMap[item]
        except KeyError:
            raise AttributeError(f"{self.__class__.__name__!r} object has no attribute '{item}'")

    def __delattr__(self, item):
        del self.boneMap[item]
        if item in self.accessedValues:
            del self.accessedValues[item]
        if item in self.renderAccessedValues:
            del self.renderAccessedValues[item]

    def __setattr__(self, key, value):
        if key in self.boneMap or isinstance(value, BaseBone):
            self.boneMap[key] = value
        elif key == "renderPreparation":
            super().__setattr__(key, value)
            self.renderAccessedValues.clear()
        else:
            super().__setattr__(key, value)

    def __repr__(self) -> str:
        return f"<SkeletonInstance of {self.skeletonCls.__name__} with {dict(self)}>"

    def __str__(self) -> str:
        return str(dict(self))

    def __len__(self) -> int:
        return len(self.boneMap)

    def clone(self):
        res = SkeletonInstance(self.skeletonCls, clonedBoneMap=copy.deepcopy(self.boneMap))
        for k, v in res.boneMap.items():
            v.isClonedInstance = True
        res.dbEntity = copy.deepcopy(self.dbEntity)
        res.accessedValues = copy.deepcopy(self.accessedValues)
        res.renderAccessedValues = copy.deepcopy(self.renderAccessedValues)
        return res

    def setEntity(self, entity: db.Entity):
        self.dbEntity = entity
        self.accessedValues = {}
        self.renderAccessedValues = {}

    def structure(self) -> dict:
        return {
            key: bone.structure() | {"sortindex": i}
            for i, (key, bone) in enumerate(self.items())
        }

    def __deepcopy__(self, memodict):
        res = self.clone()
        memodict[id(self)] = res
        return res


class BaseSkeleton(object, metaclass=MetaBaseSkel):
    """
        This is a container-object holding information about one database entity.

        It has to be sub-classed with individual information about the kindName of the entities
        and its specific data attributes, the so called bones.
        The Skeleton stores its bones in an :class:`OrderedDict`-Instance, so the definition order of the
        contained bones remains constant.

        :ivar key: This bone stores the current database key of this entity. \
        Assigning to this bones value is dangerous and does *not* affect the actual key its stored in.

        :vartype key: server.bones.BaseBone

        :ivar creationdate: The date and time where this entity has been created.
        :vartype creationdate: server.bones.DateBone

        :ivar changedate: The date and time of the last change to this entity.
        :vartype changedate: server.bones.DateBone
    """
    __viurBaseSkeletonMarker__ = True
    boneMap = None

    @classmethod
    def subSkel(cls, *name, fullClone: bool = False, **kwargs) -> SkeletonInstance:
        """
            Creates a new sub-skeleton as part of the current skeleton.

            A sub-skeleton is a copy of the original skeleton, containing only a subset of its bones.
            To define sub-skeletons, use the subSkels property of the Skeleton object.

            By passing multiple sub-skeleton names to this function, a sub-skeleton with the union of
            all bones of the specified sub-skeletons is returned.

            If an entry called "*" exists in the subSkels-dictionary, the bones listed in this entry
            will always be part of the generated sub-skeleton.

            :param name: Name of the sub-skeleton (that's the key of the subSkels dictionary); \
                        Multiple names can be specified.

            :return: The sub-skeleton of the specified type.
        """
        if not name:
            raise ValueError("Which subSkel?")
        return cls(subSkelNames=list(name), fullClone=fullClone)

    @classmethod
    def setSystemInitialized(cls):
        for attrName in dir(cls):
            bone = getattr(cls, attrName)
            if isinstance(bone, BaseBone):
                bone.setSystemInitialized()

    @classmethod
    def setBoneValue(cls, skelValues: Any, boneName: str, value: Any,
                     append: bool = False, language: Optional[str] = None) -> bool:
        """
            Allow setting a bones value without calling fromClient or assigning to valuesCache directly.
            Santy-Checks are performed; if the value is invalid, that bone flips back to its original
            (default) value and false is returned.

            :param boneName: The Bone which should be modified
            :param value: The value that should be assigned. It's type depends on the type of that bone
            :param append: If true, the given value is appended to the values of that bone instead of
                replacing it. Only supported on bones with multiple=True
            :param language: Set/append which language
            :return: Wherever that operation succeeded or not.
        """
        bone = getattr(skelValues, boneName, None)
        if not isinstance(bone, BaseBone):
            raise ValueError("%s is no valid bone on this skeleton (%s)" % (boneName, str(skelValues)))
        skelValues[boneName]  # FIXME, ensure this bone is unserialized first
        return bone.setBoneValue(skelValues, boneName, value, append, language)

    @classmethod
    def fromClient(cls, skelValues: SkeletonInstance, data: Dict[str, Union[List[str], str]],
                   allowEmptyRequired=False) -> bool:
        """
            Load supplied *data* into Skeleton.

            This function works similar to :func:`~viur.core.skeleton.Skeleton.setValues`, except that
            the values retrieved from *data* are checked against the bones and their validity checks.

            Even if this function returns False, all bones are guaranteed to be in a valid state.
            The ones which have been read correctly are set to their valid values;
            Bones with invalid values are set back to a safe default (None in most cases).
            So its possible to call :func:`~viur.core.skeleton.Skeleton.toDB` afterwards even if reading
            data with this function failed (through this might violates the assumed consistency-model).

            :param data: Dictionary from which the data is read.

            :returns: True if all data was successfully read and taken by the Skeleton's bones.\
            False otherwise (eg. some required fields where missing or invalid).
        """
        assert not allowEmptyRequired, "allowEmptyRequired is only valid on RelSkels"
        complete = len(data) > 0  # Empty values are never valid
        skelValues.errors = []

        for key, _bone in skelValues.items():
            if _bone.readOnly:
                continue
            errors = _bone.fromClient(skelValues, key, data)
            if errors:
                for err in errors:
                    err.fieldPath.insert(0, str(key))
                skelValues.errors.extend(errors)
                for error in errors:
                    is_empty = error.severity == ReadFromClientErrorSeverity.Empty and bool(_bone.required)
                    if _bone.languages and isinstance(_bone.required, (list, tuple)):
                        is_empty &= any([key, lang] == error.fieldPath
                                        for lang in _bone.required)
                    else:
                        is_empty &= error.fieldPath == [key]
                    if is_empty or error.severity == ReadFromClientErrorSeverity.Invalid or \
                        (error.severity == ReadFromClientErrorSeverity.NotSet and _bone.required and
                         _bone.isEmpty(skelValues["key"])):
                        # We'll consider empty required bones only as an error, if they're on the top-level (and not
                        # further down the hierarchy (in an record- or relational-Bone)
                        complete = False

                        if conf.debug.skeleton_from_client and cls.kindName:
                            logging.debug("%s: %s: %r", cls.kindName, error.fieldPath, error.errorMessage)

        if (len(data) == 0
            or (len(data) == 1 and "key" in data)
            or ("nomissing" in data and str(data["nomissing"]) == "1")):
            skelValues.errors = []

        return complete

    @classmethod
    def refresh(cls, skel: SkeletonInstance):
        """
            Refresh the bones current content.

            This function causes a refresh of all relational bones and their associated
            information.
        """
        logging.debug(f"""Refreshing {skel["key"]=}""")

        for key, bone in skel.items():
            if not isinstance(bone, BaseBone):
                continue

            _ = skel[key]  # Ensure value gets loaded
            bone.refresh(skel, key)

    def __new__(cls, *args, **kwargs) -> SkeletonInstance:
        return SkeletonInstance(cls, *args, **kwargs)


class MetaSkel(MetaBaseSkel):
    def __init__(cls, name, bases, dct):
        super(MetaSkel, cls).__init__(name, bases, dct)
        relNewFileName = inspect.getfile(cls) \
            .replace(str(conf.instance.project_base_path), "") \
            .replace(str(conf.instance.core_base_path), "")

        # Check if we have an abstract skeleton
        if cls.__name__.endswith("AbstractSkel"):
            # Ensure that it doesn't have a kindName
            assert cls.kindName is _undefined or cls.kindName is None, "Abstract Skeletons can't have a kindName"
            # Prevent any further processing by this class; it has to be sub-classed before it can be used
            return

        # Automatic determination of the kindName, if the class is not part of viur.core.
        if (cls.kindName is _undefined
            and not relNewFileName.strip(os.path.sep).startswith("viur")
            and not "viur_doc_build" in dir(sys)):
            if cls.__name__.endswith("Skel"):
                cls.kindName = cls.__name__.lower()[:-4]
            else:
                cls.kindName = cls.__name__.lower()
        # Try to determine which skeleton definition takes precedence
        if cls.kindName and cls.kindName is not _undefined and cls.kindName in MetaBaseSkel._skelCache:
            relOldFileName = inspect.getfile(MetaBaseSkel._skelCache[cls.kindName]) \
                .replace(str(conf.instance.project_base_path), "") \
                .replace(str(conf.instance.core_base_path), "")
            idxOld = min(
                [x for (x, y) in enumerate(conf.skeleton_search_path) if relOldFileName.startswith(y)] + [999])
            idxNew = min(
                [x for (x, y) in enumerate(conf.skeleton_search_path) if relNewFileName.startswith(y)] + [999])
            if idxNew == 999:
                # We could not determine a priority for this class as its from a path not listed in the config
                raise NotImplementedError(
                    "Skeletons must be defined in a folder listed in conf.skeleton_search_path")
            elif idxOld < idxNew:  # Lower index takes precedence
                # The currently processed skeleton has a lower priority than the one we already saw - just ignore it
                return
            elif idxOld > idxNew:
                # The currently processed skeleton has a higher priority, use that from now
                MetaBaseSkel._skelCache[cls.kindName] = cls
            else:  # They seem to be from the same Package - raise as something is messed up
                raise ValueError("Duplicate definition for %s in %s and %s" %
                                 (cls.kindName, relNewFileName, relOldFileName))
        # Ensure that all skeletons are defined in folders listed in conf.skeleton_search_path
        if (not any([relNewFileName.startswith(x) for x in conf.skeleton_search_path])
            and not "viur_doc_build" in dir(sys)):  # Do not check while documentation build
            raise NotImplementedError(
                f"""{relNewFileName} must be defined in a folder listed in {conf.skeleton_search_path}""")
        if cls.kindName and cls.kindName is not _undefined:
            MetaBaseSkel._skelCache[cls.kindName] = cls
        # Auto-Add ViUR Search Tags Adapter if the skeleton has no adapter attached
        if cls.customDatabaseAdapter is _undefined:
            cls.customDatabaseAdapter = ViurTagsSearchAdapter()


class CustomDatabaseAdapter:
    # Set to True if we can run a fulltext search using this database
    providesFulltextSearch: bool = False
    # Are results returned by `meth:fulltextSearch` guaranteed to also match the databaseQuery
    fulltextSearchGuaranteesQueryConstrains = False
    # Indicate that we can run more types of queries than originally supported by firestore
    providesCustomQueries: bool = False

    def preprocessEntry(self, entry: db.Entity, skel: BaseSkeleton, changeList: List[str], isAdd: bool) -> db.Entity:
        """
        Can be overridden to add or alter the data of this entry before it's written to firestore.
        Will always be called inside an transaction.
        :param entry: The entry containing the serialized data of that skeleton
        :param skel: The (complete) skeleton this skel.toDB() runs for
        :param changeList: List of boneNames that are changed by this skel.toDB() call
        :param isAdd: Is this an update or an add?
        :return: The (maybe modified) entity
        """
        return entry

    def updateEntry(self, dbObj: db.Entity, skel: BaseSkeleton, changeList: List[str], isAdd: bool) -> None:
        """
        Like `meth:preprocessEntry`, but runs after the transaction had completed.
        Changes made to dbObj will be ignored.
        :param entry: The entry containing the serialized data of that skeleton
        :param skel: The (complete) skeleton this skel.toDB() runs for
        :param changeList: List of boneNames that are changed by this skel.toDB() call
        :param isAdd: Is this an update or an add?
        """
        return

    def deleteEntry(self, entry: db.Entity, skel: BaseSkeleton) -> None:
        """
        Called, after an skeleton has been successfully deleted from firestore
        :param entry: The db.Entity object containing an snapshot of the data that has been deleted
        :param skel: The (complete) skeleton for which `meth:delete' had been called
        """
        return

    def fulltextSearch(self, queryString: str, databaseQuery: db.Query) -> List[db.Entity]:
        """
        If this database supports fulltext searches, this method has to implement them.
        If it's a plain fulltext search engine, leave 'prop:fulltextSearchGuaranteesQueryConstrains' set to False,
        then the server will post-process the list of entries returned from this function and drop any entry that
        cannot be returned due to other constrains set in 'param:databaseQuery'. If you can obey *every* constrain
        set in that Query, we can skip this post-processing and save some CPU-cycles.
        :param queryString: the string as received from the user (no quotation or other safety checks applied!)
        :param databaseQuery: The query containing any constrains that returned entries must also match
        :return:
        """
        raise NotImplementedError


class ViurTagsSearchAdapter(CustomDatabaseAdapter):
    """
    This Adapter implements a simple fulltext search on top of the datastore.

    On skel.toDB(), all words from String-/TextBones are collected with all *min_length* postfixes and dumped
    into the property `viurTags`. When queried, we'll run a prefix-match against this property - thus returning
    entities with either an exact match or a match within a word.

    Example:
        For the word "hello" we'll write "hello", "ello" and "llo" into viurTags.
        When queried with "hello" we'll have an exact match.
        When queried with "hel" we'll match the prefix for "hello"
        When queried with "ell" we'll prefix-match "ello" - this is only enabled when substring_matching is True.

    We'll automatically add this adapter if a skeleton has no other database adapter defined.
    """
    providesFulltextSearch = True
    fulltextSearchGuaranteesQueryConstrains = True

    def __init__(self, min_length: int = 3, max_length: int = 99, substring_matching: bool = True):
        super().__init__()
        self.min_length = min_length
        self.max_length = max_length
        self.substring_matching = substring_matching

    def _tagsFromString(self, value: str) -> Set[str]:
        """
        Extract all words including all min_length postfixes from given string
        """
        res = set()

        for tag in value.split(" "):
            tag = "".join([x for x in tag.lower() if x in conf.search_valid_chars])

            if len(tag) >= self.min_length:
                res.add(tag)

                if self.substring_matching:
                    for i in range(1, 1 + len(tag) - self.min_length):
                        res.add(tag[i:])

        return res

    def preprocessEntry(self, entry: db.Entity, skel: Skeleton, changeList: List[str], isAdd: bool) -> db.Entity:
        """
        Collect searchTags from skeleton and build viurTags
        """
        tags = set()

        for boneName, bone in skel.items():
            if bone.searchable:
                tags = tags.union(bone.getSearchTags(skel, boneName))

        entry["viurTags"] = list(chain(*[self._tagsFromString(x) for x in tags if len(x) <= self.max_length]))
        return entry

    def fulltextSearch(self, queryString: str, databaseQuery: db.Query) -> List[db.Entity]:
        """
        Run a fulltext search
        """
        keywords = list(self._tagsFromString(queryString))[:10]
        resultScoreMap = {}
        resultEntryMap = {}

        for keyword in keywords:
            qryBase = databaseQuery.clone()
            for entry in qryBase.filter("viurTags >=", keyword).filter("viurTags <", keyword + "\ufffd").run():
                if not entry.key in resultScoreMap:
                    resultScoreMap[entry.key] = 1
                else:
                    resultScoreMap[entry.key] += 1
                if not entry.key in resultEntryMap:
                    resultEntryMap[entry.key] = entry

        resultList = [(k, v) for k, v in resultScoreMap.items()]
        resultList.sort(key=lambda x: x[1], reverse=True)

        return [resultEntryMap[x[0]] for x in resultList[:databaseQuery.queries.limit]]


class SeoKeyBone(StringBone):
    """
    Special kind of StringBone saving its contents as `viurCurrentSeoKeys` into the entity's `viur` dict.
    """

    def unserialize(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> bool:
        try:
            skel.accessedValues[name] = skel.dbEntity["viur"]["viurCurrentSeoKeys"]
        except KeyError:
            skel.accessedValues[name] = self.getDefaultValue(skel)

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        # Serialize also to skel["viur"]["viurCurrentSeoKeys"], so we can use this bone in relations
        if name in skel.accessedValues:
            newVal = skel.accessedValues[name]
            if not skel.dbEntity.get("viur"):
                skel.dbEntity["viur"] = db.Entity()
            res = db.Entity()
            res["_viurLanguageWrapper_"] = True
            for language in (self.languages or []):
                if not self.indexed:
                    res.exclude_from_indexes.add(language)
                res[language] = None
                if language in newVal:
                    res[language] = self.singleValueSerialize(newVal[language], skel, name, parentIndexed)
            skel.dbEntity["viur"]["viurCurrentSeoKeys"] = res
        return True


class Skeleton(BaseSkeleton, metaclass=MetaSkel):
    kindName: str = _undefined  # To which kind we save our data to
    customDatabaseAdapter: Union[CustomDatabaseAdapter, None] = _undefined
    subSkels = {}  # List of pre-defined sub-skeletons of this type
    interBoneValidations: List[
        Callable[[Skeleton], List[ReadFromClientError]]] = []  # List of functions checking inter-bone dependencies

    __seo_key_trans = str.maketrans(
        {"<": "",
         ">": "",
         "\"": "",
         "'": "",
         "\n": "",
         "\0": "",
         "/": "",
         "\\": "",
         "?": "",
         "&": "",
         "#": ""
         })

    # The "key" bone stores the current database key of this skeleton.
    # Warning: Assigning to this bones value now *will* set the key
    # it gets stored in. Must be kept readOnly to avoid security-issues with add/edit.
    key = KeyBone(
        descr="Key"
    )

    name = StringBone(
        descr="Name",
        visible=False,
        compute=Compute(
            fn=lambda skel: str(skel["key"]),
            interval=ComputeInterval(ComputeMethod.OnWrite)
        )
    )

    # The date (including time) when this entry has been created
    creationdate = DateBone(
        descr="created at",
        readOnly=True,
        visible=False,
        indexed=True,
        compute=Compute(fn=utils.utcNow, interval=ComputeInterval(ComputeMethod.Once)),
    )

    # The last date (including time) when this entry has been updated

    changedate = DateBone(
        descr="updated at",
        readOnly=True,
        visible=False,
        indexed=True,
        compute=Compute(fn=utils.utcNow, interval=ComputeInterval(ComputeMethod.OnWrite)),
    )

    viurCurrentSeoKeys = SeoKeyBone(
        descr="SEO-Keys",
        readOnly=True,
        visible=False,
        languages=conf.i18n.available_languages
    )

    def __repr__(self):
        return "<skeleton %s with data=%r>" % (self.kindName, {k: self[k] for k in self.keys()})

    def __str__(self):
        return str({k: self[k] for k in self.keys()})

    def __init__(self, *args, **kwargs):
        super(Skeleton, self).__init__(*args, **kwargs)
        assert self.kindName and self.kindName is not _undefined, "You must set kindName on this skeleton!"

    @classmethod
    def all(cls, skelValues, **kwargs) -> db.Query:
        """
            Create a query with the current Skeletons kindName.

            :returns: A db.Query object which allows for entity filtering and sorting.
        """
        return db.Query(skelValues.kindName, srcSkelClass=skelValues, **kwargs)

    @classmethod
    def fromClient(cls, skelValues: SkeletonInstance, data: Dict[str, Union[List[str], str]],
                   allowEmptyRequired=False) -> bool:
        """
            This function works similar to :func:`~viur.core.skeleton.Skeleton.setValues`, except that
            the values retrieved from *data* are checked against the bones and their validity checks.

            Even if this function returns False, all bones are guaranteed to be in a valid state.
            The ones which have been read correctly are set to their valid values;
            Bones with invalid values are set back to a safe default (None in most cases).
            So its possible to call :func:`~viur.core.skeleton.Skeleton.toDB` afterwards even if reading
            data with this function failed (through this might violates the assumed consistency-model).

        :param data: Dictionary from which the data is read.
        :return: True, if all values have been read correctly (without errors), False otherwise
        """
        assert skelValues.renderPreparation is None, "Cannot modify values while rendering"
        assert not allowEmptyRequired, "allowEmptyRequired is only valid on RelSkels"
        # Load data into this skeleton
        complete = super().fromClient(skelValues, data)

        # Check if all unique values are available
        for boneName, boneInstance in skelValues.items():
            if boneInstance.unique:
                lockValues = boneInstance.getUniquePropertyIndexValues(skelValues, boneName)
                for lockValue in lockValues:
                    dbObj = db.Get(db.Key("%s_%s_uniquePropertyIndex" % (skelValues.kindName, boneName), lockValue))
                    if dbObj and (not skelValues["key"] or dbObj["references"] != skelValues["key"].id_or_name):
                        # This value is taken (sadly, not by us)
                        complete = False
                        errorMsg = boneInstance.unique.message
                        skelValues.errors.append(
                            ReadFromClientError(ReadFromClientErrorSeverity.Invalid, errorMsg, [boneName]))

        # Check inter-Bone dependencies
        for checkFunc in skelValues.interBoneValidations:
            errors = checkFunc(skelValues)
            if errors:
                for error in errors:
                    if error.severity.value > 1:
                        complete = False
                        if conf.debug.skeleton_from_client:
                            logging.debug("%s: %s: %r", cls.kindName, error.fieldPath, error.errorMessage)

                skelValues.errors.extend(errors)

        return complete

    @classmethod
    def fromDB(cls, skelValues: SkeletonInstance, key: Union[str, db.Key]) -> bool:
        """
            Load entity with *key* from the data store into the Skeleton.

            Reads all available data of entity kind *kindName* and the key *key*
            from the data store into the Skeleton structure's bones. Any previous
            data of the bones will discard.

            To store a Skeleton object to the data store, see :func:`~viur.core.skeleton.Skeleton.toDB`.

            :param key: A :class:`viur.core.DB.Key`, :class:`viur.core.DB.Query`, or string,\
            from which the data shall be fetched.

            :returns: True on success; False if the given key could not be found.

        """
        assert skelValues.renderPreparation is None, "Cannot modify values while rendering"
        try:
            dbKey = db.keyHelper(key, skelValues.kindName)
        except ValueError:  # This key did not parse
            return False
        dbRes = db.Get(dbKey)
        if dbRes is None:
            return False
        skelValues.setEntity(dbRes)
        skelValues["key"] = dbKey
        return True

    @classmethod
    def toDB(cls, skel: SkeletonInstance, update_relations: bool = True, **kwargs) -> db.Key:
        """
            Store current Skeleton entity to the Datastore.

            Stores the current data of this instance into the database.
            If an *key* value is set to the object, this entity will ne updated;
            Otherwise a new entity will be created.

            To read a Skeleton object from the data store, see :func:`~viur.core.skeleton.Skeleton.fromDB`.

            :param update_relations: If False, this entity won't be marked dirty;
                This avoids from being fetched by the background task updating relations.

            :returns: The datastore key of the entity.
        """
        assert skel.renderPreparation is None, "Cannot modify values while rendering"
        # fixme: Remove in viur-core >= 4
        if "clearUpdateTag" in kwargs:
            msg = "clearUpdateTag was replaced by update_relations"
            warnings.warn(msg, DeprecationWarning, stacklevel=3)
            logging.warning(msg, stacklevel=3)
            update_relations = not kwargs["clearUpdateTag"]

        def txnUpdate(write_skel):
            db_key = write_skel["key"]
            skel = write_skel.skeletonCls()

            blob_list = set()
            change_list = []
            old_copy = {}
            # Load the current values from Datastore or create a new, empty db.Entity
            is_add = not bool(db_key)
            if not db_key:
                # We'll generate the key we'll be stored under early so we can use it for locks etc
                db_key = db.AllocateIDs(db.Key(skel.kindName))
                db_obj = db.Entity(db_key)
                db_obj["viur"] = {}
                skel.dbEntity = db_obj
            else:
                db_key = db.keyHelper(db_key, skel.kindName)
                if not (db_obj := db.Get(db_key)):
                    db_obj = db.Entity(db_key)
                    skel.dbEntity = db_obj
                else:
                    skel.setEntity(db_obj)
                    old_copy = {k: v for k, v in db_obj.items()}

            db_obj.setdefault("viur", {})

            # Merge values and assemble unique properties
            # Move accessed Values from srcSkel over to skel
            skel.accessedValues = write_skel.accessedValues
            skel["key"] = db_key  # Ensure key stays set
            for bone_name, bone in skel.items():
                if bone_name == "key":  # Explicitly skip key on top-level - this had been set above
                    continue

                if not (bone_name in skel.accessedValues or bone.compute) and bone_name not in skel.dbEntity:
                    _ = skel[bone_name]  # Ensure the datastore is filled with the default value
                if (
                    bone_name in skel.accessedValues or bone.compute  # We can have a computed value on store
                    or bone_name not in skel.dbEntity  # It has not been written and is not in the database
                ):
                    # Serialize bone into entity
                    try:
                        bone.serialize(skel, bone_name, True)
                    except Exception:
                        logging.error(f"Failed to serialize {bone_name} {bone} {skel.accessedValues[bone_name]}")
                        raise


                # Obtain referenced blobs
                blob_list.update(bone.getReferencedBlobs(skel, bone_name))

                # Check if the value has actually changed
                if db_obj.get(bone_name) != old_copy.get(bone_name):
                    change_list.append(bone_name)

                # Lock hashes from bones that must have unique values
                if bone.unique:
                    # Remember old hashes for bones that must have a unique value
                    old_unique_values = db_obj["viur"].get(f"{bone_name}_uniqueIndexValue", [])

                    # Check if the property is unique
                    new_unique_values = bone.getUniquePropertyIndexValues(skel, bone_name)
                    new_lock_kind = f"{skel.kindName}_{bone_name}_uniquePropertyIndex"
                    for new_lock_value in new_unique_values:
                        new_lock_key = db.Key(new_lock_kind, new_lock_value)
                        if lock_db_obj := db.Get(new_lock_key):
                            # There's already a lock for that value, check if we hold it
                            if lock_db_obj["references"] != db_obj.key.id_or_name:
                                # This value has already been claimed, and not by us
                                raise ValueError(f"The unique value '{skel[bone_name]}' \
                                    of bone '{bone_name}' has been recently claimed!")
                        else:
                            # This value is locked for the first time, create a new lock-object
                            lock_obj = db.Entity(new_lock_key)
                            lock_obj["references"] = db_obj.key.id_or_name
                            db.Put(lock_obj)
                        if new_lock_value in old_unique_values:
                            old_unique_values.remove(new_lock_value)
                    db_obj["viur"][f"{bone_name}_uniqueIndexValue"] = new_unique_values
                    # Remove any lock-object we're holding for values that we don't have anymore
                    for old_unique_value in old_unique_values:
                        # Try to delete the old lock
                        old_lock_key = db.Key(f"{skel.kindName,}_{bone_name}_uniquePropertyIndex", old_unique_value)
                        if old_lock_obj := db.Get(old_lock_key):
                            if old_lock_obj["references"] != db_obj.key.id_or_name:
                                # We've been supposed to have that lock - but we don't.
                                # Don't remove that lock as it now belongs to a different entry
                                logging.critical("Detected Database corruption! A Value-Lock had been reassigned!")
                            else:
                                # It's our lock which we don't need anymore
                                db.Delete(old_lock_key)
                        else:
                            logging.critical("Detected Database corruption! Could not delete stale lock-object!")

            # Ensure the SEO-Keys are up-to-date
            last_requested_seo_keys = db_obj["viur"].get("viurLastRequestedSeoKeys") or {}
            last_set_seo_keys = db_obj["viur"].get("viurCurrentSeoKeys") or {}
            # Filter garbage serialized into this field by the SeoKeyBone
            last_set_seo_keys = {k: v for k, v in last_set_seo_keys.items() if not k.startswith("_") and v}

            if not isinstance(db_obj["viur"].get("viurCurrentSeoKeys"), dict):
                db_obj["viur"]["viurCurrentSeoKeys"] = {}
            if current_seo_keys := skel.getCurrentSEOKeys():
                # Convert to lower-case and remove certain characters
                for lang, value in list(current_seo_keys.items()):
                    current_seo_keys[lang] = value.lower().translate(Skeleton.__seo_key_trans).strip()

            for language in (conf.i18n.available_languages or [conf.i18n.default_language]):
                if current_seo_keys and language in current_seo_keys:
                    current_seo_key = current_seo_keys[language]
                    if current_seo_key != last_requested_seo_keys.get(language):  # This one is new or has changed
                        new_seo_key = current_seo_keys[language]
                        for _ in range(0, 3):
                            entry_using_key = db.Query(skel.kindName).filter("viur.viurActiveSeoKeys =",
                                                                             new_seo_key).getEntry()
                            if entry_using_key and entry_using_key.key != db_obj.key:
                                # It's not unique; append a random string and try again
                                new_seo_key = f"{current_seo_keys[language]}-{utils.generateRandomString(5).lower()}"
                            else:
                                # We found a new SeoKey
                                break
                        else:
                            raise ValueError("Could not generate an unique seo key in 3 attempts")
                    else:
                        new_seo_key = current_seo_key
                    last_set_seo_keys[language] = new_seo_key
                else:
                    # We'll use the database-key instead
                    last_set_seo_keys[language] = str(db_obj.key.id_or_name)
                # Store the current, active key for that language
                db_obj["viur"]["viurCurrentSeoKeys"][language] = last_set_seo_keys[language]

            db_obj["viur"].setdefault("viurActiveSeoKeys", [])

            for language, seo_key in last_set_seo_keys.items():
                if db_obj["viur"]["viurCurrentSeoKeys"][language] not in db_obj["viur"]["viurActiveSeoKeys"]:
                    # Ensure the current, active seo key is in the list of all seo keys
                    db_obj["viur"]["viurActiveSeoKeys"].insert(0, seo_key)
            if str(db_obj.key.id_or_name) not in db_obj["viur"]["viurActiveSeoKeys"]:
                # Ensure that key is also in there
                db_obj["viur"]["viurActiveSeoKeys"].insert(0, str(db_obj.key.id_or_name))
            # Trim to the last 200 used entries
            db_obj["viur"]["viurActiveSeoKeys"] = db_obj["viur"]["viurActiveSeoKeys"][:200]
            # Store lastRequestedKeys so further updates can run more efficient
            db_obj["viur"]["viurLastRequestedSeoKeys"] = current_seo_keys

            # mark entity as "dirty" when update_relations is set, to zero otherwise.
            db_obj["viur"]["delayedUpdateTag"] = time() if update_relations else 0
            db_obj = skel.preProcessSerializedData(db_obj)

            # Allow the custom DB Adapter to apply last minute changes to the object
            if skel.customDatabaseAdapter:
                db_obj = skel.customDatabaseAdapter.preprocessEntry(db_obj, skel, change_list, is_add)

            # ViUR2 import compatibility - remove properties containing. if we have a dict with the same name
            def fixDotNames(entity):
                for k, v in list(entity.items()):
                    if isinstance(v, dict):
                        for k2, v2 in list(entity.items()):
                            if k2.startswith(f"{k}."):
                                del entity[k2]
                                backupKey = k2.replace(".", "__")
                                entity[backupKey] = v2
                                entity.exclude_from_indexes = set(entity.exclude_from_indexes) | {backupKey}
                        fixDotNames(v)
                    elif isinstance(v, list):
                        for x in v:
                            if isinstance(x, dict):
                                fixDotNames(x)

            if conf.viur2import_blobsource:  # Try to fix these only when converting from ViUR2
                fixDotNames(db_obj)

            # Write the core entry back
            db.Put(db_obj)

            # Now write the blob-lock object
            blob_list = skel.preProcessBlobLocks(blob_list)
            if blob_list is None:
                raise ValueError("Did you forget to return the blob_list somewhere inside getReferencedBlobs()?")
            if None in blob_list:
                msg = f"None is not valid in {blob_list=}"
                logging.error(msg)
                raise ValueError(msg)

            if not is_add and (old_blob_lock_obj := db.Get(db.Key("viur-blob-locks", db_key.id_or_name))):
                removed_blobs = set(old_blob_lock_obj.get("active_blob_references", [])) - blob_list
                old_blob_lock_obj["active_blob_references"] = list(blob_list)
                if old_blob_lock_obj["old_blob_references"] is None:
                    old_blob_lock_obj["old_blob_references"] = [removed_blob for removed_blob in removed_blobs]
                else:
                    old_blob_refs = set(old_blob_lock_obj["old_blob_references"])
                    old_blob_refs += set([removed_blob for removed_blob in removed_blobs])  # Add removed blobs
                    old_blob_refs -= blob_list  # Remove active blobs
                    old_blob_lock_obj["old_blob_references"] = [old_blob_ref for old_blob_ref in old_blob_refs]

                old_blob_lock_obj["has_old_blob_references"] = bool(old_blob_lock_obj["old_blob_references"])
                old_blob_lock_obj["is_stale"] = False
                db.Put(old_blob_lock_obj)
            else:  # We need to create a new blob-lock-object
                blob_lock_obj = db.Entity(db.Key("viur-blob-locks", db_obj.key.id_or_name))
                blob_lock_obj["active_blob_references"] = list(blob_list)
                blob_lock_obj["old_blob_references"] = []
                blob_lock_obj["has_old_blob_references"] = False
                blob_lock_obj["is_stale"] = False
                db.Put(blob_lock_obj)

            return db_obj.key, db_obj, skel, change_list

        # END of txnUpdate subfunction
        is_add = skel["key"] is None

        # Allow bones to perform outstanding "magic" operations before saving to db
        for bone_name, _bone in skel.items():
            _bone.performMagic(skel, bone_name, isAdd=is_add)

        # Run our SaveTxn
        if db.IsInTransaction():
            key, db_obj, skel, change_list = txnUpdate(skel)
        else:
            key, db_obj, skel, change_list = db.RunInTransaction(txnUpdate, skel)

        # Perform post-save operations (postProcessSerializedData Hook, Searchindex, ..)
        skel["key"] = key

        for bone_name, bone in skel.items():
            bone.postSavedHandler(skel, bone_name, key)

        skel.postSavedHandler(key, db_obj)

        if update_relations and not is_add:
            if change_list and len(change_list) < 5:  # Only a few bones have changed, process these individually
                for idx, changed_bone in enumerate(change_list):
                    updateRelations(key, time() + 1, changed_bone, _countdown=10 * idx)
            else:  # Update all inbound relations, regardless of which bones they mirror
                updateRelations(key, time() + 1, None)

        # Inform the custom DB Adapter of the changes made to the entry
        if skel.customDatabaseAdapter:
            skel.customDatabaseAdapter.updateEntry(db_obj, skel, change_list, is_add)

        return key

    @classmethod
    def preProcessBlobLocks(cls, skelValues, locks):
        """
            Can be overridden to modify the list of blobs referenced by this skeleton
        """
        return locks

    @classmethod
    def preProcessSerializedData(cls, skelValues, entity):
        """
            Can be overridden to modify the :class:`viur.core.db.Entity` before its actually
            written to the data store.
        """
        return entity

    @classmethod
    def postSavedHandler(cls, skelValues, key, dbObj):
        """
            Can be overridden to perform further actions after the entity has been written
            to the data store.
        """
        pass

    @classmethod
    def postDeletedHandler(cls, skelValues, key):
        """
            Can be overridden to perform further actions after the entity has been deleted
            from the data store.
        """
        pass

    @classmethod
    def getCurrentSEOKeys(cls, skelValues) -> Union[None, Dict[str, str]]:
        """
        Should be overridden to return a dictionary of language -> SEO-Friendly key
        this entry should be reachable under. How theses names are derived are entirely up to the application.
        If the name is already in use for this module, the server will automatically append some random string
        to make it unique.
        :return:
        """
        return

    @classmethod
    def delete(cls, skelValues):
        """
            Deletes the entity associated with the current Skeleton from the data store.
        """

        def txnDelete(skel: SkeletonInstance):
            skelKey = skel["key"]
            dbObj = db.Get(skelKey)  # Fetch the raw object as we might have to clear locks
            viurData = dbObj.get("viur") or {}
            if dbObj.get("viur_incomming_relational_locks"):
                raise errors.Locked("This entry is locked!")
            for boneName, bone in skel.items():
                # Ensure that we delete any value-lock objects remaining for this entry
                bone.delete(skel, boneName)
                if bone.unique:
                    flushList = []
                    for lockValue in viurData.get("%s_uniqueIndexValue" % boneName) or []:
                        lockKey = db.Key("%s_%s_uniquePropertyIndex" % (skel.kindName, boneName), lockValue)
                        lockObj = db.Get(lockKey)
                        if not lockObj:
                            logging.error("Programming error detected: Lockobj %s missing!" % lockKey)
                        elif lockObj["references"] != dbObj.key.id_or_name:
                            logging.error(
                                "Programming error detected: %s did not hold lock for %s" % (skel["key"], lockKey))
                        else:
                            flushList.append(lockObj)
                    if flushList:
                        db.Delete(flushList)
            # Delete the blob-key lock object
            lockObjectKey = db.Key("viur-blob-locks", dbObj.key.id_or_name)
            lockObj = db.Get(lockObjectKey)
            if lockObj is not None:
                if lockObj["old_blob_references"] is None and lockObj["active_blob_references"] is None:
                    db.Delete(lockObjectKey)  # Nothing to do here
                else:
                    if lockObj["old_blob_references"] is None:
                        # No old stale entries, move active_blob_references -> old_blob_references
                        lockObj["old_blob_references"] = lockObj["active_blob_references"]
                    elif lockObj["active_blob_references"] is not None:
                        # Append the current references to the list of old & stale references
                        lockObj["old_blob_references"] += lockObj["active_blob_references"]
                    lockObj["active_blob_references"] = []  # There are no active ones left
                    lockObj["is_stale"] = True
                    lockObj["has_old_blob_references"] = True
                    db.Put(lockObj)
            db.Delete(skelKey)
            processRemovedRelations(skelKey)
            return dbObj

        key = skelValues["key"]
        if key is None:
            raise ValueError("This skeleton is not in the database (anymore?)!")
        skel = skeletonByKind(skelValues.kindName)()
        if not skel.fromDB(key):
            raise ValueError("This skeleton is not in the database (anymore?)!")
        if db.IsInTransaction():
            dbObj = txnDelete(skel)
        else:
            dbObj = db.RunInTransaction(txnDelete, skel)
        for boneName, _bone in skel.items():
            _bone.postDeletedHandler(skel, boneName, key)
        skel.postDeletedHandler(key)
        # Inform the custom DB Adapter
        if skel.customDatabaseAdapter:
            skel.customDatabaseAdapter.deleteEntry(dbObj, skel)


class RelSkel(BaseSkeleton):
    """
        This is a Skeleton-like class that acts as a container for Skeletons used as a
        additional information data skeleton for
        :class:`~viur.core.bones.extendedRelationalBone.extendedRelationalBone`.

        It needs to be sub-classed where information about the kindName and its attributes
        (bones) are specified.

        The Skeleton stores its bones in an :class:`OrderedDict`-Instance, so the definition order of the
        contained bones remains constant.
    """

    @classmethod
    def fromClient(cls, skelValues: SkeletonInstance, data: Dict[str, Union[List[str], str]],
                   allowEmptyRequired=False) -> bool:
        """
            Reads the data supplied by data.
            Unlike setValues, error-checking is performed.
            The values might be in a different representation than the one used in getValues/serValues.
            Even if this function returns False, all bones are guranteed to be in a valid state:
            The ones which have been read correctly contain their data; the other ones are set back to a safe default (None in most cases)
            So its possible to call save() afterwards even if reading data fromClient faild (through this might violates the assumed consitency-model!).

            :param data: Dictionary from which the data is read
            :returns: True if the data was successfully read; False otherwise (eg. some required fields where missing or invalid)
        """
        complete = len(data) > 0  # Empty values are never valid
        skelValues.errors = []
        allBonesEmpty = True  # Indicates if all bones in this skeleton are empty
        requiredBonesEmpty = False  # If True, at least one bone marked with required=True is also empty
        for key, _bone in skelValues.items():
            if _bone.readOnly:
                continue
            errors = _bone.fromClient(skelValues, key, data)
            thisBoneEmpty = False
            if errors:
                for err in errors:
                    err.fieldPath.insert(0, str(key))
                skelValues.errors.extend(errors)
                for err in errors:
                    if err.fieldPath == [key] and (err.severity == ReadFromClientErrorSeverity.Empty or
                                                   (err.severity == ReadFromClientErrorSeverity.NotSet and
                                                    _bone.isEmpty(skelValues[key]))):
                        thisBoneEmpty = True
                        if _bone.required:
                            requiredBonesEmpty = True
                    if err.severity == ReadFromClientErrorSeverity.Invalid:
                        complete = False
            allBonesEmpty &= thisBoneEmpty
        # Special Case for RecordBones that are not required, but contain required bones
        if requiredBonesEmpty and not (allBonesEmpty and allowEmptyRequired):
            # There's at least one required Bone that's empty; but either allowEmptyRequired is not true, or we have
            # at least one other bone in this skeleton, that have data; so we have to reject this skeleton
            complete = False
        if (len(data) == 0 or (len(data) == 1 and "key" in data) or (
            "nomissing" in data and str(data["nomissing"]) == "1")):
            skelValues.errors = []
            return False  # Force the skeleton to be displayed to the user again
        return complete

    def serialize(self, parentIndexed):
        if self.dbEntity is None:
            self.dbEntity = db.Entity()
        for key, _bone in self.items():
            # if key in self.accessedValues:
            _bone.serialize(self, key, parentIndexed)
        # if "key" in self:  # Write the key seperatly, as the base-bone doesn't store it
        #    dbObj["key"] = self["key"]
        # FIXME: is this a good idea? Any other way to ensure only bones present in refKeys are serialized?
        return self.dbEntity

    # return {k: v for k, v in self.valuesCache.entity.items() if k in self.__boneNames__}

    def unserialize(self, values: Union[db.Entity, dict]):
        """
            Loads 'values' into this skeleton.

            :param values: dict with values we'll assign to our bones
        """
        if not isinstance(values, db.Entity):
            self.dbEntity = db.Entity()
            self.dbEntity.update(values)
        else:
            self.dbEntity = values

        self.accessedValues = {}
        self.renderAccessedValues = {}
        # self.valuesCache = {"entity": values, "changedValues": {}, "cachedRenderValues": {}}
        return
        for bkey, _bone in self.items():
            if isinstance(_bone, BaseBone):
                if bkey == "key":
                    try:
                        # Reading the value from db.Entity
                        self.valuesCache[bkey] = str(values.key())
                    except:
                        # Is it in the dict?
                        if "key" in values:
                            self.valuesCache[bkey] = str(values["key"])
                        else:  # Ingore the key value
                            pass
                else:
                    _bone.unserialize(self.valuesCache, bkey, values)


class RefSkel(RelSkel):
    @classmethod
    def fromSkel(cls, kindName: str, *args: List[str]) -> Type[RefSkel]:
        """
            Creates a relSkel from a skeleton-class using only the bones explicitly named
            in \*args

            :param args: List of bone names we'll adapt
            :return: A new instance of RefSkel
        """
        newClass = type("RefSkelFor" + kindName, (RefSkel,), {})
        fromSkel = skeletonByKind(kindName)
        newClass.__boneMap__ = {k: v for k, v in fromSkel.__boneMap__.items() if k in args}
        return newClass


class SkelList(list):
    """
        This class is used to hold multiple skeletons together with other, commonly used information.

        SkelLists are returned by Skel().all()...fetch()-constructs and provide additional information
        about the data base query, for fetching additional entries.

        :ivar cursor: Holds the cursor within a query.
        :vartype cursor: str
    """

    __slots__ = (
        "baseSkel",
        "customQueryInfo",
        "getCursor",
        "get_orders",
        "renderPreparation",
    )

    def __init__(self, baseSkel=None):
        """
            :param baseSkel: The baseclass for all entries in this list
        """
        super(SkelList, self).__init__()
        self.baseSkel = baseSkel or {}
        self.getCursor = lambda: None
        self.get_orders = lambda: None
        self.renderPreparation = None
        self.customQueryInfo = {}


### Tasks ###

@CallDeferred
def processRemovedRelations(removedKey, cursor=None):
    updateListQuery = db.Query("viur-relations").filter("dest.__key__ =", removedKey) \
        .filter("viur_relational_consistency >", 2)
    updateListQuery = updateListQuery.setCursor(cursor)
    updateList = updateListQuery.run(limit=5)
    for entry in updateList:
        skel = skeletonByKind(entry["viur_src_kind"])()
        assert skel.fromDB(entry["src"].key)
        if entry["viur_relational_consistency"] == 3:  # Set Null
            for key, _bone in skel.items():
                if isinstance(_bone, RelationalBone):
                    relVal = skel[key]
                    if isinstance(relVal, dict) and relVal["dest"]["key"] == removedKey:
                        # FIXME: Should never happen: "key" not in relVal["dest"]
                        # skel.setBoneValue(key, None)
                        skel[key] = None
                    elif isinstance(relVal, list):
                        skel[key] = [x for x in relVal if x["dest"]["key"] != removedKey]
                    else:
                        print("Type? %s" % type(relVal))
            skel.toDB(update_relations=False)
        else:
            logging.critical("Cascading Delete to %s/%s" % (skel.kindName, skel["key"]))
            skel.delete()
            pass
    if len(updateList) == 5:
        processRemovedRelations(removedKey, updateListQuery.getCursor())


@CallDeferred
def updateRelations(destKey: db.Key, minChangeTime: int, changedBone: Optional[str], cursor: Optional[str] = None):
    """
        This function updates Entities, which may have a copy of values from another entity which has been recently
        edited (updated). In ViUR, relations are implemented by copying the values from the referenced entity into the
        entity that's referencing them. This allows ViUR to run queries over properties of referenced entities and
        prevents additional db.Get's to these referenced entities if the main entity is read. However, this forces
        us to track changes made to entities as we might have to update these mirrored values.     This is the deferred
        call from meth:`viur.core.skeleton.Skeleton.toDB()` after an update (edit) on one Entity to do exactly that.

        :param destKey: The database-key of the entity that has been edited
        :param minChangeTime: The timestamp on which the edit occurred. As we run deferred, and the entity might have
            been edited multiple times before we get acutally called, we can ignore entities that have been updated
            in the meantime as they're  already up2date
        :param changedBone: If set, we'll update only entites that have a copy of that bone. Relations mirror only
            key and name by default, so we don't have to update these if only another bone has been changed.
        :param cursor: The database cursor for the current request as we only process five entities at once and then
            defer again.
    """
    logging.debug("Starting updateRelations for %s ; minChangeTime %s, changedBone: %s, cursor: %s",
                  destKey, minChangeTime, changedBone, cursor)
    updateListQuery = db.Query("viur-relations").filter("dest.__key__ =", destKey) \
        .filter("viur_delayed_update_tag <", minChangeTime).filter("viur_relational_updateLevel =",
                                                                   RelationalUpdateLevel.Always.value)
    if changedBone:
        updateListQuery.filter("viur_foreign_keys =", changedBone)
    if cursor:
        updateListQuery.setCursor(cursor)
    updateList = updateListQuery.run(limit=5)

    def updateTxn(skel, key, srcRelKey):
        if not skel.fromDB(key):
            logging.warning(f"Cannot update stale reference to {key=} (referenced from {srcRelKey=})")
            return

        skel.refresh()
        skel.toDB(update_relations=False)

    for srcRel in updateList:
        try:
            skel = skeletonByKind(srcRel["viur_src_kind"])()
        except AssertionError:
            logging.info("Ignoring %s which refers to unknown kind %s" % (str(srcRel.key), srcRel["viur_src_kind"]))
            continue
        if db.IsInTransaction():
            updateTxn(skel, srcRel["src"].key, srcRel.key)
        else:
            db.RunInTransaction(updateTxn, skel, srcRel["src"].key, srcRel.key)
    nextCursor = updateListQuery.getCursor()
    if len(updateList) == 5 and nextCursor:
        updateRelations(destKey, minChangeTime, changedBone, nextCursor)


@CallableTask
class TaskUpdateSearchIndex(CallableTaskBase):
    """
    This tasks loads and saves *every* entity of the given module.
    This ensures an updated searchIndex and verifies consistency of this data.
    """
    key = "rebuildSearchIndex"
    name = "Rebuild search index"
    descr = "This task can be called to update search indexes and relational information."

    def canCall(self) -> bool:
        """Checks wherever the current user can execute this task"""
        user = current.user.get()
        return user is not None and "root" in user["access"]

    def dataSkel(self):
        modules = ["*"] + listKnownSkeletons()
        modules.sort()
        skel = BaseSkeleton().clone()
        skel.module = SelectBone(descr="Module", values={x: translate(x) for x in modules}, required=True)
        return skel

    def execute(self, module, *args, **kwargs):
        usr = current.user.get()
        if not usr:
            logging.warning("Don't know who to inform after rebuilding finished")
            notify = None
        else:
            notify = usr["name"]

        if module == "*":
            for module in listKnownSkeletons():
                logging.info("Rebuilding search index for module %r", module)
                self._run(module, notify)
        else:
            self._run(module, notify)

    @staticmethod
    def _run(module: str, notify: str):
        Skel = skeletonByKind(module)
        if not Skel:
            logging.error("TaskUpdateSearchIndex: Invalid module")
            return
        RebuildSearchIndex.startIterOnQuery(Skel().all(), {"notify": notify, "module": module})


class RebuildSearchIndex(QueryIter):
    @classmethod
    def handleEntry(cls, skel: SkeletonInstance, customData: Dict[str, str]):
        skel.refresh()
        skel.toDB(update_relations=False)

    @classmethod
    def handleFinish(cls, totalCount: int, customData: Dict[str, str]):
        QueryIter.handleFinish(totalCount, customData)
        if not customData["notify"]:
            return
        txt = (
            f"{conf.instance.project_id}: Rebuild search index finished for {customData['module']}\n\n"
            f"ViUR finished to rebuild the search index for module {customData['module']}.\n"
            f"{totalCount} records updated in total on this kind."
        )
        try:
            email.sendEMail(dests=customData["notify"], stringTemplate=txt, skel=None)
        except Exception as exc:  # noqa; OverQuota, whatever
            logging.exception(f'Failed to notify {customData["notify"]}')


### Vacuum Relations

@CallableTask
class TaskVacuumRelations(TaskUpdateSearchIndex):
    """
    Checks entries in viur-relations and verifies that the src-kind
    and it's RelationalBone still exists.
    """
    key = "vacuumRelations"
    name = "Vacuum viur-relations (dangerous)"
    descr = "Drop stale inbound relations for the given kind"

    def execute(self, module: str, *args, **kwargs):
        usr = current.user.get()
        if not usr:
            logging.warning("Don't know who to inform after rebuilding finished")
            notify = None
        else:
            notify = usr["name"]
        processVacuumRelationsChunk(module.strip(), None, notify=notify)


@CallDeferred
def processVacuumRelationsChunk(
    module: str, cursor, count_total: int = 0, count_removed: int = 0, notify=None
):
    """
    Processes 25 Entries and calls the next batch
    """
    query = db.Query("viur-relations")
    if module != "*":
        query.filter("viur_src_kind =", module)
    query.setCursor(cursor)
    for relation_object in query.run(25):
        count_total += 1
        if not (src_kind := relation_object.get("viur_src_kind")):
            logging.critical("We got an relation-object without a src_kind!")
            continue
        if not (src_prop := relation_object.get("viur_src_property")):
            logging.critical("We got an relation-object without a src_prop!")
            continue
        try:
            skel = skeletonByKind(src_kind)()
        except AssertionError:
            # The referenced skeleton does not exist in this data model -> drop that relation object
            logging.info(f"Deleting {relation_object.key} which refers to unknown kind {src_kind}")
            db.Delete(relation_object)
            count_removed += 1
            continue
        if src_prop not in skel:
            logging.info(f"Deleting {relation_object.key} which refers to "
                         f"non-existing RelationalBone {src_prop} of {src_kind}")
            db.Delete(relation_object)
            count_removed += 1
    logging.info(f"END processVacuumRelationsChunk {module}, "
                 f"{count_total} records processed, {count_removed} removed")
    if new_cursor := query.getCursor():
        # Start processing of the next chunk
        processVacuumRelationsChunk(module, new_cursor, count_total, count_removed, notify)
    elif notify:
        txt = (
            f"{conf.instance.project_id}: Vacuum relations finished for {module}\n\n"
            f"ViUR finished to vacuum viur-relations for module {module}.\n"
            f"{count_total} records processed, "
            f"{count_removed} entries removed"
        )
        try:
            email.sendEMail(dests=notify, stringTemplate=txt, skel=None)
        except Exception as exc:  # noqa; OverQuota, whatever
            logging.exception(f"Failed to notify {notify}")


# Forward our references to SkelInstance to the database (needed for queries)
db.config["SkeletonInstanceRef"] = SkeletonInstance
