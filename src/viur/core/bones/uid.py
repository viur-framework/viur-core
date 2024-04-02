import secrets
import string
import warnings

import logging
import typing as t

from viur.core import current, db, utils
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity, UniqueValue, \
    UniqueLockMethod


class UidBone(BaseBone):
    """
    The "StringBone" represents a data field that contains text values.
    """
    type = "str"

    def __init__(
        self,
        *,
        length: int | None = 13,
        pattern: str | None = "*",
        generate_fn: t.Callable | None = None,
        unique=UniqueValue(UniqueLockMethod.SameValue, False,"Unique Value already in use"),
        **kwargs
    ):
        """
        Initializes a new UidBone.


        :param length: The length allowed for values of this bone.
        :param kwargs: Inherited arguments from the BaseBone.
        """
        # fixme: Remove in viur-core >= 4

        super().__init__(unique=unique, **kwargs)

        if self.multiple or self.languages:
            raise ValueError("UidBone cannot be multiple or translated")
        if not self.readOnly:
            self.readOnly = True
            # raise ValueError("UidBone must be readOnly")

        self.length = length
        self.pattern = pattern
        self.generate_fn = generate_fn

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        logging.error("seri")
        logging.error(skel.accessedValues[name])

        if super().serialize(skel, name, parentIndexed):
            return True
        else:
            logging.error("generate new id")
            skel.dbEntity[name] = self.generate_uid()
            return True

    def unserialize(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> bool:
        logging.error("unseri")
        logging.error(skel.dbEntity[name])
        if name in skel.dbEntity:
            skel.accessedValues[name] = skel.dbEntity[name]
        else:
            skel.accessedValues[name] = self.generate_uid()

        return True

    def generate_uid(self):
        if "*" in self.pattern and "?" not in self.pattern and "#" not in self.pattern:
            return self.pattern.replace("*", utils.string.random(self.length))
        res = self.pattern
        remaining_chars = self.length
        if "?" in self.pattern:
            while "?" in res:
                remaining_chars -= 1
                res = res.replace("?", utils.string.random(1), 1)
        if "#" in self.pattern:
            while "#" in res:
                remaining_chars -= 1
                res = res.replace("#", secrets.choice(string.digits), 1)
        return res.replace("*", utils.string.random(remaining_chars))

    def structure(self) -> dict:
        ret = super().structure() | {
            "length": self.length,
            "pattern": self.pattern
        }
        return ret
