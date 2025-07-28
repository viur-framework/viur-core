from __future__ import annotations  # noqa: required for pre-defined annotations

import copy
import fnmatch
import typing as t
import warnings

from functools import partial
from ..bones.base import BaseBone
from .skeleton import Skeleton
from viur.core import db


class SkeletonInstance:
    """
        The actual wrapper around a Skeleton-Class. An object of this class is what's actually returned when you
        call a Skeleton-Class. With ViUR3, you don't get an instance of a Skeleton-Class any more - it's always this
        class. This is much faster as this is a small class.
    """
    __slots__ = {
        "_cascade_deletion",
        "accessedValues",
        "boneMap",
        "dbEntity",
        "errors",
        "is_cloned",
        "renderAccessedValues",
        "renderPreparation",
        "skeletonCls",
    }

    def __init__(
        self,
        skel_cls: t.Type[Skeleton],
        entity: t.Optional[db.Entity | dict] = None,
        *,
        bones: t.Iterable[str] = (),
        bone_map: t.Optional[t.Dict[str, BaseBone]] = None,
        clone: bool = False,
        # FIXME: BELOW IS DEPRECATED!
        clonedBoneMap: t.Optional[t.Dict[str, BaseBone]] = None,
    ):
        """
        Creates a new SkeletonInstance based on `skel_cls`.

        :param skel_cls: Is the base skeleton class to inherit from and reference to.
        :param bones: If given, defines an iterable of bones that are take into the SkeletonInstance.
            The order of the bones defines the order in the SkeletonInstance.
        :param bone_map: A pre-defined bone map to use, or extend.
        :param clone: If set True, performs a cloning of the used bone map, to be entirely stand-alone.
        """

        # TODO: Remove with ViUR-core 3.8; required by viur-datastore :'-(
        if clonedBoneMap:
            msg = "'clonedBoneMap' was renamed into 'bone_map'"
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            # logging.warning(msg, stacklevel=2)

            if bone_map:
                raise ValueError("Can't provide both 'bone_map' and 'clonedBoneMap'")

            bone_map = clonedBoneMap

        bone_map = bone_map or {}

        if bones:
            names = ("key",) + tuple(bones)

            # generate full keys sequence based on definition; keeps order of patterns!
            keys = []
            for name in names:
                if name in skel_cls.__boneMap__:
                    keys.append(name)
                else:
                    keys.extend(fnmatch.filter(skel_cls.__boneMap__.keys(), name))

            if clone:
                bone_map |= {k: copy.deepcopy(skel_cls.__boneMap__[k]) for k in keys if skel_cls.__boneMap__[k]}
            else:
                bone_map |= {k: skel_cls.__boneMap__[k] for k in keys if skel_cls.__boneMap__[k]}

        elif clone:
            if bone_map:
                bone_map = copy.deepcopy(bone_map)
            else:
                bone_map = copy.deepcopy(skel_cls.__boneMap__)

        # generated or use provided bone_map
        if bone_map:
            self.boneMap = bone_map

        else:  # No Subskel, no Clone
            self.boneMap = skel_cls.__boneMap__.copy()

        if clone:
            for v in self.boneMap.values():
                v.isClonedInstance = True

        self._cascade_deletion = False
        self.accessedValues = {}
        self.dbEntity = entity
        self.errors = []
        self.is_cloned = clone
        self.renderAccessedValues = {}
        self.renderPreparation = None
        self.skeletonCls = skel_cls

    def items(self, yieldBoneValues: bool = False) -> t.Iterable[tuple[str, BaseBone]]:
        if yieldBoneValues:
            for key in self.boneMap.keys():
                yield key, self[key]
        else:
            yield from self.boneMap.items()

    def keys(self) -> t.Iterable[str]:
        yield from self.boneMap.keys()

    def values(self) -> t.Iterable[t.Any]:
        yield from self.boneMap.values()

    def __iter__(self) -> t.Iterable[str]:
        yield from self.keys()

    def __contains__(self, item):
        return item in self.boneMap

    def __bool__(self):
        return bool(self.accessedValues or self.dbEntity)

    def get(self, item, default=None):
        if item not in self:
            return default

        return self[item]

    def update(self, *args, **kwargs) -> None:
        self.__ior__(dict(*args, **kwargs))

    def __setitem__(self, key, value):
        assert self.renderPreparation is None, "Cannot modify values while rendering"
        if isinstance(value, BaseBone):
            raise AttributeError(f"Don't assign this bone object as skel[\"{key}\"] = ... anymore to the skeleton. "
                                 f"Use skel.{key} = ... for bone to skeleton assignment!")
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

    def __getattr__(self, item: str):
        """
        Get a special attribute from the SkeletonInstance

        __getattr__ is called when an attribute access fails with an
        AttributeError. So we know that this is not a real attribute of
        the SkeletonInstance. But there are still a few special cases in which
        attributes are loaded from the skeleton class.
        """
        if item == "boneMap":
            return {}  # There are __setAttr__ calls before __init__ has run

        # Load attribute value from the Skeleton class
        elif item in {
            "database_adapters",
            "interBoneValidations",
            "kindName",
        }:
            return getattr(self.skeletonCls, item)

        # FIXME: viur-datastore backward compatiblity REMOVE WITH VIUR4
        elif item == "customDatabaseAdapter":
            if prop := getattr(self.skeletonCls, "database_adapters"):
                return prop[0]  # viur-datastore assumes there is only ONE!

            return None

        # Load a @classmethod from the Skeleton class and bound this SkeletonInstance
        elif item in {
            "all",
            "delete",
            "patch",
            "fromClient",
            "fromDB",
            "getCurrentSEOKeys",
            "postDeletedHandler",
            "postSavedHandler",
            "preProcessBlobLocks",
            "preProcessSerializedData",
            "read",
            "readonly",
            "refresh",
            "serialize",
            "setBoneValue",
            "toDB",
            "unserialize",
            "write",
        }:
            return partial(getattr(self.skeletonCls, item), self)

        # Load a @property from the Skeleton class
        try:
            # Use try/except to save an if check
            class_value = getattr(self.skeletonCls, item)

        except AttributeError:
            # Not inside the Skeleton class, okay at this point.
            pass

        else:
            if isinstance(class_value, property):
                # The attribute is a @property and can be called
                # Note: `self` is this SkeletonInstance, not the Skeleton class.
                #       Therefore, you can access values inside the property method
                #       with item-access like `self["key"]`.
                try:
                    return class_value.fget(self)
                except AttributeError as exc:
                    # The AttributeError cannot be re-raised any further at this point.
                    # Since this would then be evaluated as an access error
                    # to the property attribute.
                    # Otherwise, it would be lost that it is an incorrect attribute access
                    # within this property (during the method call).
                    msg, *args = exc.args
                    msg = f"AttributeError: {msg}"
                    raise ValueError(msg, *args) from exc
        # Load the bone instance from the bone map of this SkeletonInstance
        try:
            return self.boneMap[item]
        except KeyError as exc:
            raise AttributeError(f"{self.__class__.__name__!r} object has no attribute '{item}'") from exc

    def __delattr__(self, item):
        del self.boneMap[item]
        if item in self.accessedValues:
            del self.accessedValues[item]
        if item in self.renderAccessedValues:
            del self.renderAccessedValues[item]

    def __setattr__(self, key, value):
        if key in self.boneMap or isinstance(value, BaseBone):
            if value is None:
                del self.boneMap[key]
            else:
                value.__set_name__(self.skeletonCls, key)
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

    def __ior__(self, other: dict | SkeletonInstance | db.Entity) -> SkeletonInstance:
        if isinstance(other, dict):
            for key, value in other.items():
                self.setBoneValue(key, value)
        elif isinstance(other, db.Entity):
            new_entity = self.dbEntity or db.Entity()
            # We're not overriding the key
            for key, value in other.items():
                new_entity[key] = value
            self.setEntity(new_entity)
        elif isinstance(other, SkeletonInstance):
            for key, value in other.accessedValues.items():
                self.accessedValues[key] = value
            for key, value in other.dbEntity.items():
                self.dbEntity[key] = value
        else:
            raise ValueError("Unsupported Type")
        return self

    def clone(self, *, apply_clone_strategy: bool = False) -> t.Self:
        """
        Clones a SkeletonInstance into a modificable, stand-alone instance.
        This will also allow to modify the underlying data model.
        """
        res = SkeletonInstance(self.skeletonCls, bone_map=self.boneMap, clone=True)
        if apply_clone_strategy:
            for bone_name, bone_instance in self.items():
                bone_instance.clone_value(res, self, bone_name)
        else:
            res.accessedValues = copy.deepcopy(self.accessedValues)
        res.dbEntity = copy.deepcopy(self.dbEntity)
        res.is_cloned = True
        if not apply_clone_strategy:
            res.renderAccessedValues = copy.deepcopy(self.renderAccessedValues)
        # else: Depending on the strategy the values are cloned in bone_instance.clone_value too

        return res

    def ensure_is_cloned(self):
        """
        Ensured this SkeletonInstance is a stand-alone clone, which can be modified.
        Does nothing in case it was already cloned before.
        """
        if not self.is_cloned:
            return self.clone()

        return self

    def setEntity(self, entity: db.Entity):
        self.dbEntity = entity
        self.accessedValues = {}
        self.renderAccessedValues = {}

    def structure(self) -> dict:
        return {
            key: bone.structure() | {"sortindex": i}
            for i, (key, bone) in enumerate(self.items())
        }

    def dump(self):
        """
        Return a simplified version of the bone values in this skeleton.
        This can be used for example in the JSON renderer.
        """

        return {
            bone_name: bone.dump(self, bone_name) for bone_name, bone in self.items()
        }

    def __deepcopy__(self, memodict):
        res = self.clone()
        memodict[id(self)] = res
        return res
