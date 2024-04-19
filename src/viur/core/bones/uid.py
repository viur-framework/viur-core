import typing as t

from viur.core import db
from viur.core.bones.base import BaseBone, Compute, ComputeInterval, ComputeMethod, UniqueValue, UniqueLockMethod


def generate_uid(skel, bone):
    def transac(_key):
        for i in range(3):
            try:
                if db_obj := db.Get(_key):
                    db_obj["count"] += 1
                    db.Put(db_obj)
                else:
                    db_obj = db.Entity(_key)
                    db_obj["count"] = 0
                    db.Put(db_obj)
                break
            except:  # recall the function
                import time
                time.sleep(i + 1)
        else:
            raise ValueError("Can't not set the Uid")
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
    The "UidBone" represents a data field that contains text values.
    """
    type = "uid"

    def __init__(
        self,
        *,
        generate_fn: t.Callable = generate_uid,
        fill_chars="",
        length: int = 13,
        pattern: str | t.Callable | None = "*",
        **kwargs
    ):
        """
        Initializes a new UidBone.


        :param generate_fn: The compute function to calculate the unique value,
        :param fill_chars: The chars that are filed in when the uid has not the length.
        :param length: The length allowed for values of this bone.
        :param pattern: The pattern for this Bone. "*" will be replaced with the uid value.
        :param kwargs: Inherited arguments from the BaseBone.
        """
        super().__init__(
            compute=Compute(fn=generate_fn, interval=ComputeInterval(ComputeMethod.Once)),
            unique=UniqueValue(UniqueLockMethod.SameValue, False, "Unique Value already in use"),
            **kwargs
        )

        if self.multiple or self.languages:
            raise ValueError("UidBone cannot be multiple or translated")
        if not self.readOnly:
            self.readOnly = True

        self.fill_chars = str(fill_chars)
        self.length = length
        if isinstance(pattern, t.Callable):
            pattern = pattern()
        self.pattern = str(pattern)
        if self.pattern.count("*") != 1:
            raise ValueError("Only one Wildcard (*) is allowed in the pattern")

    def structure(self) -> dict:
        ret = super().structure() | {
            "fill_chars": self.fill_chars,
            "length": self.length,
            "pattern": self.pattern
        }
        return ret
