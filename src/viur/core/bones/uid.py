import secrets
import string
import warnings

import logging
import typing as t

from viur.core import current, db, utils
from viur.core.bones.base import BaseBone, Compute, ComputeInterval, ComputeMethod, ReadFromClientError, \
    ReadFromClientErrorSeverity, \
    UniqueValue, \
    UniqueLockMethod


def generate_uid(bone):
    if "*" in bone.pattern and "?" not in bone.pattern and "#" not in bone.pattern:
        return bone.pattern.replace("*", utils.string.random(bone.length))
    res = bone.pattern
    remaining_chars = bone.length
    if "?" in bone.pattern:
        while "?" in res:
            remaining_chars -= 1
            res = res.replace("?", utils.string.random(1), 1)
    if "#" in bone.pattern:
        while "#" in res:
            remaining_chars -= 1
            res = res.replace("#", secrets.choice(string.digits), 1)
    return res.replace("*", utils.string.random(remaining_chars))


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
        compute: Compute = Compute(fn=generate_uid, interval=ComputeInterval(ComputeMethod.Once)),
        unique=UniqueValue(UniqueLockMethod.SameValue, False, "Unique Value already in use"),
        **kwargs
    ):
        """
        Initializes a new UidBone.


        :param length: The length allowed for values of this bone.
        :param kwargs: Inherited arguments from the BaseBone.
        """
        # fixme: Remove in viur-core >= 4

        super().__init__(compute=compute, unique=unique, **kwargs)

        if self.multiple or self.languages:
            raise ValueError("UidBone cannot be multiple or translated")
        if not self.readOnly:
            self.readOnly = True
            # raise ValueError("UidBone must be readOnly")

        self.length = length
        self.pattern = pattern

    def structure(self) -> dict:
        ret = super().structure() | {
            "length": self.length,
            "pattern": self.pattern
        }
        return ret
