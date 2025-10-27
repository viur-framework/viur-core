from __future__ import annotations  # noqa: required for pre-defined annotations

import typing as t
import fnmatch

from .. import db, utils
from .meta import BaseSkeleton
from .utils import skeletonByKind


class RelSkel(BaseSkeleton):
    """
        This is a Skeleton-like class that acts as a container for Skeletons used as a
        additional information data skeleton for :class:`~viur.core.bones.relational.RelationalBone`.

        It needs to be sub-classed where information about the kindName and its attributes
        (bones) are specified.

        The Skeleton stores its bones in an :class:`OrderedDict`-Instance, so the definition order of the
        contained bones remains constant.
    """

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

    def unserialize(self, values: db.Entity | dict):
        """
            Loads 'values' into this skeleton.

            :param values: dict with values we'll assign to our bones
        """
        if not isinstance(values, db.Entity):
            self.dbEntity = db.Entity()

            if values:
                self.dbEntity.update(values)
        else:
            self.dbEntity = values

        self.accessedValues = {}
        self.renderAccessedValues = {}


class RefSkel(RelSkel):
    @classmethod
    def fromSkel(cls, kindName: str, *args: list[str]) -> t.Type[RefSkel]:
        """
            Creates a ``RefSkel`` from a skeleton-class using only the bones explicitly named in ``args``.

            :param args: List of bone names we'll adapt
            :return: A new instance of RefSkel
        """
        newClass = type("RefSkelFor" + kindName, (RefSkel,), {})
        fromSkel = skeletonByKind(kindName)
        newClass.kindName = kindName
        bone_map = {}
        for arg in args:
            bone_map |= {k: fromSkel.__boneMap__[k] for k in fnmatch.filter(fromSkel.__boneMap__.keys(), arg)}
        newClass.__boneMap__ = bone_map
        return newClass

    def read(
        self,
        key: t.Optional[db.Key | str | int] = None,
        *,
        subskel: t.Iterable[str] = (),
        bones: t.Iterable[str] = (),
    ) -> "SkeletonInstance":
        """
        Read full skeleton instance referenced by the RefSkel from the database.

        Can be used for reading the full Skeleton from a RefSkel.
        The `key` parameter also allows to read another, given key from the related kind.

        :param key: Can be used to overwrite the key; Ohterwise, the RefSkel's key-property will be used.
        :param subskel: Optionally form skel from subskels
        :param bones: Optionally create skeleton only from the specified bones

        :raise ValueError: If the entry is no longer in the database.
        """
        skel_cls = skeletonByKind(self.kindName)

        if subskel or bones:
            skel = skel_cls.subskel(*utils.ensure_iterable(subskel), bones=utils.ensure_iterable(bones))
        else:
            skel = skel_cls()

        if not skel.read(key or self["key"]):
            raise ValueError(f"""The key {key or self["key"]!r} seems to be gone""")

        return skel
