import typing as t
from viur.core import db
from viur.core.bones.base import BaseBone, Compute, ComputeInterval, ComputeMethod, UniqueValue, UniqueLockMethod


def generate_number(db_key: db.Key) -> int:
    """
        The generate_number method generates a leading number that is always unique per entry.
    """

    def transact(_key: db.Key):
        # A commit conflict only surfaces when the surrounding transaction commits and is
        # retried by db.run_in_transaction, so it must propagate out of this function.
        if db_obj := db.get(_key):
            db_obj["count"] += 1
        else:
            db_obj = db.Entity(_key)
            db_obj["count"] = 0
        db.put(db_obj)
        return db_obj["count"]

    if db.is_in_transaction():
        return transact(db_key)
    else:
        return db.run_in_transaction(transact, db_key)


def generate_uid(skel, bone):
    db_key = db.Key("viur-uids", f"{skel.kindName}-{bone.name}-uid")
    count_value = generate_number(db_key)
    if bone.fillchar:
        # The wildcard itself is replaced, so it does not count towards the length of the prefix.
        length_to_fill = bone.length - (len(bone.pattern) - 1)
        res = str(count_value).rjust(length_to_fill, bone.fillchar)
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
        fillchar: str = "0",
        length: int = 13,
        pattern: str | t.Callable | None = "*",
        **kwargs
    ):
        """
        Initializes a new UidBone.

        :param generate_fn: The compute function to calculate the unique value,
        :param fillchar The char that are filed in when the uid has not the length.
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
            raise ValueError("UidBone must be read-only")

        self.fillchar = str(fillchar)
        self.length = length
        if isinstance(pattern, t.Callable):
            pattern = pattern()
        self.pattern = str(pattern)
        if self.pattern.count("*") != 1:
            raise ValueError("Only one wildcard (*) is allowed and required in the pattern")
        if len(self.fillchar) != 1:
            raise ValueError("Only one char is allowed as fillchar")

    def structure(self) -> dict:
        ret = super().structure() | {
            "fillchar": self.fillchar,
            "length": self.length,
            "pattern": self.pattern
        }
        return ret
