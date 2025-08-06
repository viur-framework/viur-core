import fnmatch
import inspect
import logging
import os
import string
import sys
import typing as t
from deprecated.sphinx import deprecated
from .adapter import ViurTagsSearchAdapter
from ..bones.base import BaseBone, ReadFromClientErrorSeverity, getSystemInitialized
from .. import db, utils
from ..config import conf


_UNDEFINED_KINDNAME = object()
ABSTRACT_SKEL_CLS_SUFFIX = "AbstractSkel"
KeyType: t.TypeAlias = db.Key | str | int


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
        "errors",
        "fromClient",
        "fromDB",
        "get",
        "getCurrentSEOKeys",
        "items",
        "keys",
        "limit",
        "orderby",
        "orderdir",
        "patch",
        "postDeletedHandler",
        "postSavedHandler",
        "preProcessBlobLocks",
        "preProcessSerializedData",
        "read",
        "readonly",
        "refresh",
        "self",
        "serialize",
        "setBoneValue",
        "structure",
        "style",
        "toDB",
        "unserialize",
        "values",
        "write",
    }

    __allowed_chars = string.ascii_letters + string.digits + "_"

    def __init__(cls, name, bases, dct, **kwargs):
        cls.__boneMap__ = MetaBaseSkel.generate_bonemap(cls)

        if not getSystemInitialized() and not cls.__name__.endswith(ABSTRACT_SKEL_CLS_SUFFIX):
            MetaBaseSkel._allSkelClasses.add(cls)

        super().__init__(name, bases, dct)

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

    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        if isinstance(value, BaseBone):
            # Call BaseBone.__set_name__ manually for bones that are assigned at runtime
            value.__set_name__(self, key)


class MetaSkel(MetaBaseSkel):

    def __init__(cls, name, bases, dct, **kwargs):
        super().__init__(name, bases, dct, **kwargs)

        relNewFileName = inspect.getfile(cls) \
            .replace(str(conf.instance.project_base_path), "") \
            .replace(str(conf.instance.core_base_path), "")

        # Check if we have an abstract skeleton
        if cls.__name__.endswith(ABSTRACT_SKEL_CLS_SUFFIX):
            # Ensure that it doesn't have a kindName
            assert cls.kindName is _UNDEFINED_KINDNAME or cls.kindName is None, \
                "Abstract Skeletons can't have a kindName"
            # Prevent any further processing by this class; it has to be sub-classed before it can be used
            return

        # Automatic determination of the kindName, if the class is not part of viur.core.
        if (
                cls.kindName is _UNDEFINED_KINDNAME
                and not relNewFileName.strip(os.path.sep).startswith("viur")
                and "viur_doc_build" not in dir(sys)  # do not check during documentation build
        ):
            if cls.__name__.endswith("Skel"):
                cls.kindName = cls.__name__.lower()[:-4]
            else:
                cls.kindName = cls.__name__.lower()

        # Try to determine which skeleton definition takes precedence
        if cls.kindName and cls.kindName is not _UNDEFINED_KINDNAME and cls.kindName in MetaBaseSkel._skelCache:
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
                raise ValueError(f"Duplicate definition for {cls.kindName} in {relNewFileName} and {relOldFileName}")

        # Ensure that all skeletons are defined in folders listed in conf.skeleton_search_path
        if (
                not any([relNewFileName.startswith(path) for path in conf.skeleton_search_path])
                and "viur_doc_build" not in dir(sys)  # do not check during documentation build
        ):
            raise NotImplementedError(
                f"""{relNewFileName} must be defined in a folder listed in {conf.skeleton_search_path}""")

        if cls.kindName and cls.kindName is not _UNDEFINED_KINDNAME:
            MetaBaseSkel._skelCache[cls.kindName] = cls

        # Auto-Add ViUR Search Tags Adapter if the skeleton has no adapter attached
        if cls.database_adapters is _UNDEFINED_KINDNAME:
            cls.database_adapters = ViurTagsSearchAdapter()

        # Always ensure that skel.database_adapters is an iterable
        cls.database_adapters = utils.ensure_iterable(cls.database_adapters)


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
    @deprecated(
        version="3.7.0",
        reason="Function renamed. Use subskel function as alternative implementation.",
    )
    def subSkel(cls, *subskel_names, fullClone: bool = False, **kwargs) -> "SkeletonInstance":
        return cls.subskel(*subskel_names, clone=fullClone)  # FIXME: REMOVE WITH VIUR4

    @classmethod
    def subskel(
        cls,
        *names: str,
        bones: t.Iterable[str] = (),
        clone: bool = False,
    ) -> "SkeletonInstance":
        """
            Creates a new sub-skeleton from the current skeleton.

            A sub-skeleton is a copy of the original skeleton, containing only a subset of its bones.

            Sub-skeletons can either be defined using the the subSkels property of the Skeleton object,
            or freely by giving patterns for bone names which shall be part of the sub-skeleton.

            1. Giving names as parameter merges the bones of all Skeleton.subSkels-configurations together.
               This is the usual behavior. By passing multiple sub-skeleton names to this function, a sub-skeleton
               with the union of all bones of the specified sub-skeletons is returned. If an entry called "*"
               exists in the subSkels-dictionary, the bones listed in this entry will always be part of the
               generated sub-skeleton.
            2. Given the *bones* parameter allows to freely specify a sub-skeleton; One specialty here is,
               that the order of the bones can also be changed in this mode. This mode is the new way of defining
               sub-skeletons, and might become the primary way to define sub-skeletons in future.
            3. Both modes (1 + 2) can be combined, but then the original order of the bones is kept.
            4. The "key" bone is automatically available in each sub-skeleton.
            5. An fnmatch-compatible wildcard pattern is allowed both in the subSkels-bone-list and the
               free bone list.

            Example (TodoSkel is the example skeleton from viur-base):
            ```py
            # legacy mode (see 1)
            subskel = TodoSkel.subskel("add")
            # creates subskel: key, firstname, lastname, subject

            # free mode (see 2) allows to specify a different order!
            subskel = TodoSkel.subskel(bones=("subject", "message", "*stname"))
            # creates subskel: key, subject, message, firstname, lastname

            # mixed mode (see 3)
            subskel = TodoSkel.subskel("add", bones=("message", ))
            # creates subskel: key, firstname, lastname, subject, message
            ```

            :param bones: Allows to specify an iterator of bone names (more precisely, fnmatch-wildards) which allow
                to freely define a subskel. If *only* this parameter is given, the order of the specification also
                defines, the order of the list. Otherwise, the original order as defined in the skeleton is kept.
            :param clone: If set True, performs a cloning of the used bone map, to be entirely stand-alone.

            :return: The sub-skeleton of the specified type.
        """
        from_subskel = False
        bones = list(bones)

        for name in names:
            # a str refers to a subskel name from the cls.subSkel dict
            if isinstance(name, str):
                # add bones from "*" subskel once
                if not from_subskel:
                    bones.extend(cls.subSkels.get("*") or ())
                    from_subskel = True

                bones.extend(cls.subSkels.get(name) or ())

            else:
                raise ValueError(f"Invalid subskel definition: {name!r}")

        if from_subskel:
            # when from_subskel is True, create bone names based on the order of the bones in the original skeleton
            bones = tuple(k for k in cls.__boneMap__.keys() if any(fnmatch.fnmatch(k, n) for n in bones))

        if not bones:
            raise ValueError("The given subskel definition doesn't contain any bones!")

        return cls(bones=bones, clone=clone)

    @classmethod
    def setSystemInitialized(cls):
        for attrName in dir(cls):
            bone = getattr(cls, attrName)
            if isinstance(bone, BaseBone):
                bone.setSystemInitialized()

    @classmethod
    def setBoneValue(
        cls,
        skel: "SkeletonInstance",
        boneName: str,
        value: t.Any,
        append: bool = False,
        language: t.Optional[str] = None
    ) -> bool:
        """
            Allows for setting a bones value without calling fromClient or assigning a value directly.
            Sanity-Checks are performed; if the value is invalid, that bone flips back to its original
            (default) value and false is returned.

            :param boneName: The name of the bone to be modified
            :param value: The value that should be assigned. It's type depends on the type of that bone
            :param append: If True, the given value is appended to the values of that bone instead of
                replacing it. Only supported on bones with multiple=True
            :param language: Language to set

            :return: Wherever that operation succeeded or not.
        """
        bone = getattr(skel, boneName, None)

        if not isinstance(bone, BaseBone):
            raise ValueError(f"{boneName!r} is no valid bone on this skeleton ({skel!r})")

        if language:
            if not bone.languages:
                raise ValueError("The bone {boneName!r} has no language setting")
            elif language not in bone.languages:
                raise ValueError("The language {language!r} is not available for bone {boneName!r}")

        if value is None:
            if append:
                raise ValueError("Cannot append None-value to bone {boneName!r}")

            if language:
                skel[boneName][language] = [] if bone.multiple else None
            else:
                skel[boneName] = [] if bone.multiple else None

            return True

        _ = skel[boneName]  # ensure the bone is being unserialized first
        return bone.setBoneValue(skel, boneName, value, append, language)

    @classmethod
    def fromClient(
        cls,
        skel: "SkeletonInstance",
        data: dict[str, list[str] | str],
        *,
        amend: bool = False,
        ignore: t.Optional[t.Iterable[str]] = None,
    ) -> bool:
        """
            Load supplied *data* into Skeleton.

            This function works similar to :func:`~viur.core.skeleton.Skeleton.setValues`, except that
            the values retrieved from *data* are checked against the bones and their validity checks.

            Even if this function returns False, all bones are guaranteed to be in a valid state.
            The ones which have been read correctly are set to their valid values;
            Bones with invalid values are set back to a safe default (None in most cases).
            So its possible to call :func:`~viur.core.skeleton.Skeleton.write` afterwards even if reading
            data with this function failed (through this might violates the assumed consistency-model).

            :param skel: The skeleton instance to be filled.
            :param data: Dictionary from which the data is read.
            :param amend: Defines whether content of data may be incomplete to amend the skel,
                which is useful for edit-actions.
            :param ignore: optional list of bones to be ignored; Defaults to all readonly-bones when set to None.

            :returns: True if all data was successfully read and complete. \
            False otherwise (e.g. some required fields where missing or where invalid).
        """
        complete = True
        skel.errors = []

        for key, bone in skel.items():
            if (ignore is None and bone.readOnly) or key in (ignore or ()):
                continue

            if errors := bone.fromClient(skel, key, data):
                for error in errors:
                    # insert current bone name into error's fieldPath
                    error.fieldPath.insert(0, str(key))

                    # logging.debug(f"BaseSkel.fromClient {key=} {error=}")

                    incomplete = (
                        # always when something is invalid
                        error.severity == ReadFromClientErrorSeverity.Invalid
                        or (
                            # only when path is top-level
                            len(error.fieldPath) == 1
                            and (
                                # bone is generally required
                                bool(bone.required)
                                and (
                                    # and value is either empty
                                    error.severity == ReadFromClientErrorSeverity.Empty
                                    # or when not amending, not set
                                    or (not amend and error.severity == ReadFromClientErrorSeverity.NotSet)
                                )
                            )
                        )
                    )

                    # in case there are language requirements, test additionally
                    if bone.languages and isinstance(bone.required, (list, tuple)):
                        incomplete &= any([key, lang] == error.fieldPath for lang in bone.required)

                    # logging.debug(f"BaseSkel.fromClient {incomplete=} {error.severity=} {bone.required=}")

                    if incomplete:
                        complete = False

                        if conf.debug.skeleton_from_client:
                            logging.error(
                                f"""{getattr(cls, "kindName", cls.__name__)}: {".".join(error.fieldPath)}: """
                                f"""({error.severity}) {error.errorMessage}"""
                            )
                    else:
                        errors.clear()

                skel.errors += errors

        return complete

    @classmethod
    def refresh(cls, skel: "SkeletonInstance"):
        """
            Refresh the bones current content.

            This function causes a refresh of all relational bones and their associated
            information.
        """
        logging.debug(f"""Refreshing {skel["key"]!r} ({skel.get("name")!r})""")

        for key, bone in skel.items():
            if not isinstance(bone, BaseBone):
                continue

            _ = skel[key]  # Ensure value gets loaded
            bone.refresh(skel, key)

    @classmethod
    def readonly(cls, skel: "SkeletonInstance"):
        """
            Set all bones to readonly in the Skeleton.
        """
        for bone in skel.values():
            if not isinstance(bone, BaseBone):
                continue
            bone.readOnly = True

    def __new__(cls, *args, **kwargs) -> "SkeletonInstance":
        from .instance import SkeletonInstance
        return SkeletonInstance(cls, *args, **kwargs)
