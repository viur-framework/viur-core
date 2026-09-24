"""
The constants, global variables and container classes used in the datastore api
"""
from __future__ import annotations

import datetime
import enum
import typing as t
from contextvars import ContextVar
from dataclasses import dataclass, field
from ..config import conf

KEY_SPECIAL_PROPERTY = "_id"
"""The property name pointing to an entities key in a query.

On MongoDB ``_id`` is the field the id really lives in — a plain key like any other, no pseudo property."""

VALUE_TYPES = None | str | int | float | bool | datetime.datetime | datetime.date | datetime.time
"""Types that can be used as a property value in a query.

A key is a plain ``str`` (the ``_id``), which the union already covers — it needs no type of its own."""

current_db_access_log: ContextVar[set[str] | None] = ContextVar("Database-Accesslog", default=None)
"""If set to a set for the current thread/request, we'll log all entities / kinds accessed"""


class SortOrder(enum.Enum):
    """
    Defines possible types of sort orders for queries.
    """

    Ascending = 1
    """Sort A->Z"""
    Descending = 2
    """Sort Z->A"""
    InvertedAscending = 3
    """Fetch Z->A, then flip the results (useful in pagination to go from a start cursor backwards).

    A cursor is a position *between* two rows, not at a row itself, so reading backwards from it includes the
    row right before that position again — the one that issued the cursor. Handing the cursor of an
    ``Ascending`` query to an otherwise identical ``InvertedAscending`` query therefore returns exactly the last
    row(s) of the forward page once more, in display order; to really step back one needs the cursor of the
    page BEFORE that."""
    InvertedDescending = 4
    """Fetch A->Z, then flip the results (useful in pagination) — the counterpart of ``InvertedAscending`` for a
    ``Descending`` base order, with the same property (see there)."""

    @classmethod
    def from_str(cls, ident: str | int) -> SortOrder:
        """
        Parses a string defining a sort order into a db.SortOrder.
        """
        match str(ident or "").lower():
            case "desc" | "descending" | "1":
                return SortOrder.Descending
            case "inverted_asc" | "inverted_ascending" | "2":
                return SortOrder.InvertedAscending
            case "inverted_desc" | "inverted_descending" | "3":
                return SortOrder.InvertedDescending
            case _:  # everything else
                return SortOrder.Ascending


class QueryOrder(t.NamedTuple):
    """A named tuple describing a single sort order for a datastore query."""
    name: str
    order: SortOrder = SortOrder.Ascending


TOrders: t.TypeAlias = list[QueryOrder]
TFilters: t.TypeAlias = dict[str, VALUE_TYPES | list[VALUE_TYPES]]
TOrFilters: t.TypeAlias = list[list[tuple[str, VALUE_TYPES | list[VALUE_TYPES]]]]


@dataclass
class QueryDefinition:
    """
    A single Query that will be run against the datastore.
    """

    kind: str | None
    """The datastore kind to run the query on. Can be None for kindles queries."""

    filters: TFilters
    """A dictionary of constrains to apply to the query."""

    orders: TOrders | None
    """The list of fields to sort the results by."""

    distinct: list[str] | None = None
    """If set, a list of fields that we should return distinct values of"""

    or_filters: "TOrFilters" = field(default_factory=list)
    """Each entry is a list of (filterStr, value) pairs that are OR-ed together.
    Multiple entries are AND-ed with each other and with the AND filters."""

    limit: int = field(init=False)
    """The maximum amount of entities that should be returned"""

    startCursor: dict | None = None
    """The keyset continuation: the sort values of the last row seen, ``{"<sort field>": value, ..., "_id": id}``.
    ``Query.setCursor`` fills this field from the public, base64 encoded cursor — a plain value, not an opaque
    token."""

    endCursor: dict | None = None
    """The upper keyset bound, in the same shape as ``startCursor``: only rows that lie *before* this row in the
    current order (``_before_condition``). Whether a cursor acts as the lower or the upper bound is decided
    solely by the parameter it is passed to."""

    currentCursor: dict | None = None
    """Set after this query ran: the same shape as ``startCursor``, taken from the last row returned in query
    order."""

    def __post_init__(self):
        self.limit = conf.db.query_default_limit
