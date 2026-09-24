"""ObjectIds as strings.

Generating them and reading their timestamp is delegated to ``bson.ObjectId`` from pymongo, which is fork- and
thread-safe. This module only pins the contract viur-core needs and ``bson`` does not give by itself: an id is a
``str`` of exactly 24 lowercase hex characters. ``bson`` also accepts uppercase and twelve raw bytes, and both
would be a second spelling of the same id — a source of silent inequality, because ``doc["_id"] == value`` must
never fail over the spelling.
"""
import datetime
import string
import typing as t

from bson import ObjectId

_HEX: t.Final[frozenset[str]] = frozenset(string.hexdigits.lower())


def new_id() -> str:
    """A new ObjectId as a 24 character lowercase hex string, monotonic within a second."""
    return str(ObjectId())


def is_valid(value: t.Any) -> bool:
    """Exactly 24 lowercase hex characters in a ``str``, nothing else."""
    return isinstance(value, str) and len(value) == 24 and set(value) <= _HEX


def timestamp(value: str) -> datetime.datetime:
    """The creation time from the first four bytes, timezone aware (UTC).

    :raises ValueError: When *value* is not a valid id.
    """
    if not is_valid(value):
        raise ValueError(f"Not a valid ObjectId: {value!r}")
    return ObjectId(value).generation_time
