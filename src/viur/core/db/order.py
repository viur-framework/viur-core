"""The BSON comparison order, used to verify the order of an elided sort client-side.

Firestore returns the order of the hinted index when no ``sort()`` is sent — observed, not promised.
``transport.run_single_filter`` therefore checks every result against the requested order, and that comparison
has to mirror Mongo's type ordering, or a document holding ``None`` next to one holding an ``int`` would raise a
``TypeError`` instead of comparing.

The order (the official BSON comparison order, as far as viur documents use it): null/missing < numbers <
strings < objects < arrays < binary < ObjectId < boolean < date. An array as a sort value counts with its
smallest (ascending) or largest (descending) element, like Mongo itself.
"""
from __future__ import annotations

import datetime
import typing as t

from bson import ObjectId

from .utils import dotted_get


def _rank(value: t.Any) -> tuple:
    if value is None:
        return (0, 0)
    if isinstance(value, bool):  # before int: bool is a subtype of int
        return (7, value)
    if isinstance(value, (int, float)):
        return (1, value)
    if isinstance(value, str):
        return (2, value)
    if isinstance(value, dict):
        return (3, 0)
    if isinstance(value, list):
        return (4, 0)
    if isinstance(value, (bytes, bytearray)):
        return (5, bytes(value))
    if isinstance(value, ObjectId):
        return (6, value.binary)
    if isinstance(value, datetime.datetime):
        return (8, value.timestamp())
    return (9, repr(value))


class _Reversed:
    """Inverts the order of a key, so a descending field can sit next to ascending ones in a plain tuple."""
    __slots__ = ("key",)

    def __init__(self, key: tuple):
        self.key = key

    def __lt__(self, other: "_Reversed") -> bool:
        return other.key < self.key

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Reversed):
            return other.key == self.key
        return self.key == other


def bson_sort_key(value: t.Any, direction: int) -> t.Any:
    """A comparable key for *value* in *direction* (``1``/``-1``)."""
    if isinstance(value, list):
        scalars = [_rank(v) for v in value if not isinstance(v, list)]
        key = (min(scalars) if direction == 1 else max(scalars)) if scalars else _rank(None)
    else:
        key = _rank(value)
    return key if direction == 1 else _Reversed(key)


def is_sorted(docs: list[dict], sort: list[tuple[str, int]]) -> bool:
    """Do *docs* lie in the order *sort* asks for, lexicographically over all of its fields?

    Equal keys are allowed.

    :param docs: The documents as the driver returned them.
    :param sort: The Mongo sort the documents are checked against.
    :return: ``True`` when the order holds.
    """
    # FIXME: objects and nested arrays only compare by their type rank, so a sort on such a field passes this
    #        check without really matching Mongo's own order. Sorting on a scalar or a multikey field is exact.
    def key(doc: dict) -> tuple:
        return tuple(bson_sort_key(dotted_get(doc, field), direction) for field, direction in sort)

    previous = None
    for doc in docs:
        current = key(doc)
        if previous is not None and current < previous:
            return False
        previous = current
    return True
