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


def generate_uid(skel, bone):
    def transac(_key):

        if db_obj := db.Get(_key):
            db_obj["count"] += 1
            db.Put(db_obj)
        else:
            db_obj = db.Entity(_key)
            db_obj["count"] = 0
            db.Put(db_obj)
        return db_obj["count"]

    db_key = db.Key("viur-uids", f"{skel.kindName}-{bone.name}-uid")
    if db.IsInTransaction():
        count_value = transac(db_key)
    else:
        count_value = db.RunInTransaction(transac, db_key)
    if bone.fill_chars:
        length_to_fill = bone.length - len(bone.pattern)
        res = str(count_value).rjust(length_to_fill, bone.fill_chars)
        return bone.pattern.replace("*", res)
    else:
        return bone.pattern.replace("*", str(count_value))


class UidBone(BaseBone):
    """
    The "StringBone" represents a data field that contains text values.
    """
    type = "str"

    def __init__(
        self,
        *,
        fill_chars="",
        length: int | None = 13,
        pattern: str | t.Callable | None = "*",
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

        self.fill_chars = str(fill_chars)
        self.length = length
        if isinstance(pattern, t.Callable):
            pattern = pattern()
        self.pattern = str(pattern)
        if self.pattern.count("*") != 1:
            raise ValueError("Only one Wildcard (*) is allowed in the pattern")

    def structure(self) -> dict:
        ret = super().structure() | {
            "length": self.length,
            "pattern": self.pattern
        }
        return ret
