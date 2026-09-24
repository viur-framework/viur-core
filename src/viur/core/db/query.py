from __future__ import annotations

import base64
import copy
import functools
import hashlib
import json
import logging
import typing as t

from viur.core.config import conf
from viur.core.utils import json as vjson
from .transport import count, get, run_single_filter
from .types import (
    VALUE_TYPES,
    QueryDefinition,
    QueryOrder,
    SortOrder,
    TFilters,
    TOrders,
    TOrFilters,
)
from . import utils

if t.TYPE_CHECKING:
    from viur.core.skeleton import SkeletonInstance, SkelList

TOrderHook = t.TypeVar("TOrderHook", bound=t.Callable[["Query", TOrders], TOrders])
TFilterHook = t.TypeVar("TFilterHook", bound=t.Callable[
    ["Query", str, VALUE_TYPES | list[VALUE_TYPES]], TFilters
])


def _entryMatchesQuery(
    entry: dict,
    singleFilter: dict,
    or_filters: TOrFilters | None = None,
) -> bool:
    """
    Utility function which checks if the given entity could have been returned by a query filtering by the
    properties in singleFilter. This can be used if a list of entities have been retrieved (e.g. by a 3rd party
    full text search engine) and these have now to be checked against the filter returned by their modules
    :meth:`viur.core.prototypes.list.listFilter` method.
    :param entry: The entity which will be tested
    :param singleFilter: A dictionary containing all the filters from the query
    :param or_filters: Optional list of OR groups; each group is a list of (filterStr, value) pairs
    :return: True if the entity could have been returned by such an query, False otherwise
    """

    def doesMatch(entryValue: t.Any, requestedValue: t.Any, opcode: str) -> bool:
        if isinstance(entryValue, list):
            return any([doesMatch(x, requestedValue, opcode) for x in entryValue])
        if opcode == "=" and entryValue == requestedValue:
            return True
        elif opcode == "<" and entryValue < requestedValue:
            return True
        elif opcode == ">" and entryValue > requestedValue:
            return True
        elif opcode == "<=" and entryValue <= requestedValue:
            return True
        elif opcode == ">=" and entryValue >= requestedValue:
            return True
        elif opcode == "IN" and entryValue in requestedValue:
            return True
        elif opcode == "NOT_IN" and entryValue not in requestedValue:
            return True
        # any()-semantics for multi-value properties: list dispatch above handles iteration
        elif opcode == "!=" and entryValue != requestedValue:
            return True
        return False

    for filterStr, filterValue in singleFilter.items():
        field, opcode = filterStr.split(" ")
        entryValue = entry.get(field)
        if not doesMatch(entryValue, filterValue, opcode):
            return False

    if or_filters:
        for or_group in or_filters:
            if not any(
                doesMatch(entry.get(fs.split(" ", 1)[0]), v, fs.split(" ", 1)[1])
                for fs, v in or_group
            ):
                return False

    return True


_OPS = {"<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte", "IN": "$in", "NOT_IN": "$nin", "!=": "$ne"}
"""viur comparison operator -> Mongo operator."""


_LEGACY_KEY = "__key__"
"""The old Datastore pseudo name. A literal on purpose and not ``KEY_SPECIAL_PROPERTY``: that constant reads
``"_id"`` today, while ``__key__`` filters coming from consumers that have not been ported yet still have to be
translated onto ``_id``."""


def _mongo_field(name: str) -> str:
    """``__key__`` becomes ``_id`` — at the top level as well as inside a dotted path."""
    return "_id" if name == _LEGACY_KEY else name.replace(f".{_LEGACY_KEY}", "._id")


def _split(key: str) -> tuple[str, str]:
    """Split a viur filter key (``"field op"``) into field and operator."""
    # ``Query.filter`` always stores the key as f"{field} {op}" and a field itself holds no space, so
    # ``rpartition`` splits at the actual operator.
    name, _, op = key.rpartition(" ")
    return _mongo_field(name), (op or "=")


def _to_mongo_filter(filters: dict, or_filters: list) -> dict:
    """Translate viur filters (``{"field op": value}``) into a Mongo filter.

    Several ``=`` on the same field arrive as a list (``Query.filter`` appends them) and mean AND, which is
    ``$all`` in Mongo. *or_filters* is a list of groups: OR inside a group, AND between the groups.

    :param filters: The viur AND filters.
    :param or_filters: The viur OR groups.
    :return: The Mongo filter.
    """
    out: dict = {}
    for key, value in filters.items():
        field, op = _split(key)
        if op == "=":
            if isinstance(value, list):
                out.setdefault(field, {})["$all"] = value
            else:
                out[field] = value
        else:
            out.setdefault(field, {})[_OPS[op]] = value
    groups = []
    for group in or_filters:
        groups.append({"$or": [_to_mongo_filter({k: v}, []) for k, v in group]})
    if groups:
        out = {"$and": [out, *groups]} if out else ({"$and": groups} if len(groups) > 1 else groups[0])
        if isinstance(out, dict) and "$and" in out and len(out["$and"]) == 1:
            out = out["$and"][0]
    return out


_INEQUALITY_OPS = frozenset({"<", "<=", ">", ">="})


def _implicit_orders(filters: dict) -> list[tuple[str, SortOrder]]:
    """The order the Datastore gave a query without ``order`` silently: ascending by its inequality field."""
    # Exactly one field with </<=/>/>= yields [(field, Ascending)], anything else []: several operators on the
    # same field count as one, two different inequality fields the Datastore never allowed, and IN/!= are no
    # range filters. Only ``filters`` count, never ``or_filters``. Without this order an index (…, field, _id)
    # could not carry the sort elision and the range filter would stay residual.
    fields = {field for field, op in (_split(k) for k in filters) if op in _INEQUALITY_OPS}
    return [(fields.pop(), SortOrder.Ascending)] if len(fields) == 1 else []


def _to_mongo_sort(orders) -> list[tuple[str, int]]:
    """The Mongo order, with ``_id`` appended as the last criterion.

    Without an explicit criterion the order is not deterministic, and keyset pagination needs a unique
    tiebreaker. ``Inverted*`` flips the fetch direction; ``run_single_filter`` flips the result back, so it
    appears in display order.
    """
    out = []
    for name, order in orders:
        desc = order in (SortOrder.Descending, SortOrder.InvertedAscending)
        out.append((_mongo_field(name), -1 if desc else 1))
    if not any(f == "_id" for f, _ in out):
        last_dir = out[-1][1] if out else 1
        out.append(("_id", last_dir))
    return out


_ORDER_FAMILY = {
    SortOrder.Ascending: 1, SortOrder.InvertedAscending: 1,
    SortOrder.Descending: -1, SortOrder.InvertedDescending: -1,
}
"""Only the *display* direction counts for the cursor hash, not the concrete ``SortOrder``: an
``InvertedAscending`` query reads exactly the same ascending order backwards from a cursor, so a cursor issued
by an ``Ascending`` query has to be accepted by an ``InvertedAscending`` one on the same field (and the other
way round for ``Descending``/``InvertedDescending``). Hashing the raw enum value instead would tell all four
directions apart, and every backwards continuation would already fail ``setCursor``'s hash check."""


def _cursor_hash(qd: QueryDefinition) -> str:
    """Binds a cursor to its query.

    A keyset cursor is readable and changeable, unlike an opaque Datastore token. The hash upholds the old
    promise that a foreign or manipulated cursor cannot reach documents outside the current filters:
    ``setCursor`` rejects a cursor whose hash differs, and even a matching hash with a forged ``after`` value
    stays without effect outside the filter, because that filter runs along via ``$and`` on continuation.

    :return: The first 16 hex characters of the material's SHA256.
    """
    # Hashed are the *effective* orders, the shape in which orders reach ``_to_mongo_sort``. A cursor issued
    # for a differently ordered version of the same query would otherwise be accepted and then run into an
    # unhandled KeyError over a sort field its value package does not hold; this way it fails with a ValueError.
    orders = qd.orders or _implicit_orders(qd.filters or {})
    material = json.dumps(
        [
            qd.kind,
            sorted(qd.filters.items(), key=str),
            qd.or_filters,
            [(name, _ORDER_FAMILY[order]) for name, order in orders],
            qd.distinct,
        ],
        default=str, sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def _range_condition(field: str, op: str, value: t.Any) -> dict:
    """One comparison of the keyset chain, corrected for MongoDB's type bracketing.

    ``$lt``/``$gt`` and their friends only compare within the same BSON type bracket, and ``null`` (like a
    missing field) forms its own, lowest bracket: ``$gt null`` matches nothing at all, not even real values,
    while ``$lt``/``$lte`` against a real value never match a missing field although it sorts below every
    real value. Both cases are rewritten here, every other combination is already correct as it stands.

    :return: The condition; ``{}`` when the comparison constrains nothing.
    """
    if value is None:
        # "greater than the minimum of every order" is "present and not null"; ">= the minimum" is everything.
        if op == "$gt":
            return {field: {"$ne": None}}
        # Defensive: today's chains always end at _id, which is never None, so this branch is unreachable.
        if op == "$gte":
            return {}
        return {field: {op: value}}
    if op in ("$lt", "$lte"):
        # A missing or null field lies below every real value and has to be caught in addition.
        return {"$or": [{field: {op: value}}, {field: None}]}
    return {field: {op: value}}


def _after_condition(sort: list[tuple[str, int]], after: dict, *, inclusive: bool = False) -> dict:
    """The keyset continuation ``(a, b, ..., _id) > (va, vb, ..., vid)``, as an ``$or`` chain per sort field.

    *sort* is already the Mongo order from ``_to_mongo_sort``, for an ``Inverted*`` order therefore the
    direction actually queried. The equality prefixes match a missing field just like ``None``, and the
    comparison per chain link comes from :func:`_range_condition`.

    :param inclusive: Make the last link (always ``_id``) inclusive — an ``Inverted*`` query reads the row that
        issued the cursor again, a plain continuation must not, or consecutive pages would overlap.
    """
    clauses = []
    last = len(sort) - 1
    for i, (field, direction) in enumerate(sort):
        prefix = {sort[j][0]: after[sort[j][0]] for j in range(i)}
        is_last = inclusive and i == last
        if direction == 1:
            op = "$gte" if is_last else "$gt"
        else:
            op = "$lte" if is_last else "$lt"
        clauses.append({**prefix, **_range_condition(field, op, after[field])})
    return {"$or": clauses}


def _before_condition(sort: list[tuple[str, int]], before: dict) -> dict:
    """The upper keyset bound for ``endCursor``: :func:`_after_condition` with every direction flipped.

    The bound is always inclusive at the last, unique link (``_id``): a cursor is a position *between* two
    rows, and the row that issued it still belongs "before" it. Only so does ``setCursor(c1, c2)``, with the
    cursors taken after page 1 and after page 2, return page 2 in full instead of losing its last element.
    """
    clauses = []
    last = len(sort) - 1
    for i, (field, direction) in enumerate(sort):
        prefix = {sort[j][0]: before[sort[j][0]] for j in range(i)}
        is_last = i == last
        if direction == 1:
            op = "$lte" if is_last else "$lt"
        else:
            op = "$gte" if is_last else "$gt"
        clauses.append({**prefix, **_range_condition(field, op, before[field])})
    return {"$or": clauses}


def _dotted_get(doc: dict, path: str) -> t.Any:
    """Read a possibly dotted field (``"dest.name"``, as relational and spatial sorts produce it).

    A plain ``doc.get(path)`` would only find a literal top level key holding a dot, never the nested value
    Mongo itself addresses through exactly this dot notation.
    """
    value: t.Any = doc
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


class Query(object):
    """
    Base Class for querying the database. Its API still resembles the historical
    google.cloud.datastore.query API this module replaced, because callers across the
    codebase depend on that shape, and it provides the necessary hooks for relational
    or random queries, the fulltext search as well as support for IN filters.
    """

    def __init__(self, kind: str, srcSkelClass: t.Union["SkeletonInstance", None] = None, *args, **kwargs):
        """
        Constructs a new Query.
        :param kind: The kind to run this query on. This may be later overridden to run on a different kind (like
            viur-relations), but it's guaranteed to return only entities of that kind.
        :param srcSkelClass: If set, enables data-model depended queries (like relational queries) as well as the
            :meth:fetch method
        """
        super().__init__()
        self.kind = kind
        self.srcSkel = srcSkelClass
        self.queries: t.Union[None, QueryDefinition, t.List[QueryDefinition]] = QueryDefinition(kind, {}, [])
        self._filterHook: TFilterHook | None = None
        self._orderHook: TOrderHook | None = None
        # Sometimes, the default merge functionality from MultiQuery is not sufficient
        self._customMultiQueryMerge: t.Callable[[Query, list[list[dict]], int], list[dict]] | None \
            = None
        # Some (Multi-)Queries need a different amount of results per subQuery than actually returned
        self._calculateInternalMultiQueryLimit: t.Union[None, t.Callable[[Query, int], int]] = None
        # Allow carrying custom data along with the query.
        # Currently only used by SpatialBone to record the guaranteed correctness
        self.customQueryInfo = {}
        self.origKind = kind
        self._lastEntry = None
        self._fulltextQueryString: t.Union[None, str] = None
        self.lastCursor = None
        # if not kind.startswith("viur") and not kwargs.get("_excludeFromAccessLog"):
        #     accessLog = current_db_access_log.get()
        #     if isinstance(accessLog, set):
        #         accessLog.add(kind)

    def setFilterHook(self, hook: TFilterHook) -> TFilterHook | None:
        """
        Installs *hook* as a callback function for new filters.

        *hook* will be called each time a new filter constrain is added to the query.
        This allows e.g. the relationalBone to rewrite constrains added after the initial
        processing of the query has been done (e.g. by ``listFilter()`` methods).

        :param hook: The function to register as callback.
            A value of None removes the currently active hook.
        :returns: The previously registered hook (if any), or None.
        """
        old = self._filterHook
        self._filterHook = hook
        return old

    def setOrderHook(self, hook: TOrderHook) -> TOrderHook | None:
        """
        Installs *hook* as a callback function for new orderings.

        *hook* will be called each time a :func:`db.Query.order` is called on this query.

        :param hook: The function to register as callback.
            A value of None removes the currently active hook.
        :returns: The previously registered hook (if any), or None.
        """
        old = self._orderHook
        self._orderHook = hook
        return old

    def mergeExternalFilter(self, filters: dict) -> t.Self:
        """
        Safely merges filters according to the data model.

        Its only valid to call this function if the query has been created using
        :func:`core.skeleton.Skeleton.all`.

        It's safe to pass filters received from an external source (a user);
        unknown/invalid filters will be ignored, so the query-object is kept in a
        valid state even when processing malformed data.

        If complex queries are needed (e.g. filter by relations), this function
        shall also be used.

        See also :meth:`filter` for simple filters.

        :param filters: A dictionary of attributes and filter pairs.
        :returns: Returns the query itself for chaining.
        """
        if self.srcSkel is None:
            raise NotImplementedError("This query has not been created using skel.all()")

        if self.queries is None:  # This query is already unsatisfiable and adding more constraints won't change this
            return self

        skel = self.srcSkel

        if "search" in filters:
            if self.srcSkel.customDatabaseAdapter and self.srcSkel.customDatabaseAdapter.providesFulltextSearch:
                self._fulltextQueryString = str(filters["search"])
            else:
                logging.warning(
                    "Got a fulltext search query for %s which does not have a suitable customDatabaseAdapter"
                    % self.srcSkel.kindName
                )
                self.queries = None

        bones = [(y, x) for x, y in skel.items()]

        try:
            # Process filters first
            for bone, key in bones:
                bone.buildDBFilter(key, skel, self, filters)

            # Parse orders
            for bone, key in bones:
                bone.buildDBSort(key, skel, self, filters)

        except RuntimeError as e:
            logging.exception(e)
            self.queries = None
            return self

        startCursor = endCursor = None

        if "cursor" in filters and filters["cursor"] and filters["cursor"].lower() != "none":
            startCursor = filters["cursor"]

        if "endcursor" in filters and filters["endcursor"] and filters["endcursor"].lower() != "none":
            endCursor = filters["endcursor"]

        if startCursor or endCursor:
            try:
                self.setCursor(startCursor, endCursor)
            except (ValueError, KeyError, TypeError) as e:
                # setCursor() rejects a cursor carrying a foreign query hash with a ValueError, and broken
                # base64/JSON does the same (ValueError/KeyError/TypeError, depending on how far the parsing
                # gets). A cursor arrives here from an external request (see the docstring above: "safe to pass
                # filters received from an external source"), so the same rule as for any other broken filter
                # value in this function applies: ignore and log it instead of turning it into a 500.
                logging.warning(f"Ignoring invalid cursor for query on {self.kind!r}: {e!r}")

        if limit := filters.get("limit"):
            try:
                limit = int(limit)

                # disallow limit beyond conf.db.query_external_limit
                if limit > conf.db.query_external_limit:
                    limit = conf.db.query_external_limit

                # forbid any limit < 0, which might bypass defaults
                if limit < 0:
                    limit = 0

                self.limit(limit)
            except ValueError:
                pass  # ignore this

        return self

    def filter(self, prop: str, value: VALUE_TYPES | list[VALUE_TYPES]) -> t.Self:
        """
        Adds a new constraint to this query.

        See also :meth:`mergeExternalFilter` for a safer filter implementation.

        :param prop: Name of the property + operation we'll filter by
        :param value: The value of that filter.
        :returns: Returns the query itself for chaining.
        """
        if self.queries is None:
            # This query is already unsatisfiable and adding more constrains to this won't change this
            return self
        if self._filterHook is not None:
            try:
                r = self._filterHook(self, prop, value)
            except RuntimeError:
                self.queries = None
                return self
            if r is None:
                # The Hook did something special directly on 'self' to apply that filter,
                # no need for us to do anything
                return self
            prop, value = r
        if " " not in prop:
            field = prop
            op = "="
        else:
            field, op = prop.split(" ")

        # Normalize to uppercase for native Datastore operators passed as lowercase
        op = op.upper() if op.upper() in {"IN", "NOT_IN"} else op

        if op in {"IN", "!=", "NOT_IN"} and not isinstance(self.queries, list):
            if f"{field} {op}" in self.queries.filters:
                raise ValueError(f"Cannot use multiple {op} filters on the same field '{field}'")

        filterStr = f"{field} {op}"
        if isinstance(self.queries, list):
            for singleFilter in self.queries:
                if filterStr not in singleFilter.filters:
                    singleFilter.filters[filterStr] = value
                else:
                    if not isinstance(singleFilter.filters[filterStr], list):
                        singleFilter.filters[filterStr] = [singleFilter.filters[filterStr]]
                    singleFilter.filters[filterStr].append(value)
        else:
            if filterStr not in self.queries.filters:
                self.queries.filters[filterStr] = value
            else:
                if not isinstance(self.queries.filters[filterStr], list):
                    self.queries.filters[filterStr] = [self.queries.filters[filterStr]]
                self.queries.filters[filterStr].append(value)

        # The Datastore demanded that an inequality filter (</<=/>/>=) appear as the first sort criterion, and
        # that used to be added here automatically. MongoDB knows no such restriction — sorting by any field is
        # always possible, filtered or not — so the automatism is gone; whoever needs a certain order still
        # calls order() explicitly.
        return self

    def or_filter(self, *conditions: tuple[str, VALUE_TYPES]) -> t.Self:
        """
        Add an OR composite filter group.

        Each call appends one OR group; multiple calls produce multiple groups
        that are AND-ed together with each other and with any regular filters.

        Example — continent is Africa OR Asia::

            q.or_filter(("continent =", "Africa"), ("continent =", "Asia"))

        Example — two independent OR groups (both must match)::

            q.or_filter(("continent =", "Africa"), ("continent =", "Asia"))
            q.or_filter(("sortindex >", 200), ("sortindex <", 50))

        :param conditions: One or more ``("field op", value)`` pairs to OR together.
        :returns: Returns the query itself for chaining.
        """
        if self.queries is None:
            return self

        parsed = []
        for prop, value in conditions:
            if " " not in prop:
                field, op = prop, "="
            else:
                field, op = prop.split(" ", 1)
            op = op.upper() if op.upper() in {"IN", "NOT_IN"} else op
            parsed.append((f"{field} {op}", value))

        if isinstance(self.queries, list):
            for q in self.queries:
                q.or_filters.append(parsed)
        else:
            self.queries.or_filters.append(parsed)
        return self

    def order(self, *orderings: QueryOrder | t.Tuple[str, SortOrder] | str) -> t.Self:
        """
        Specify a query sorting.

        Resulting entities will be sorted by the first property argument, then by the
        second, and so on.

        The following example

        .. code-block:: python

            query = Query("Person")
            query.order(
                db.QueryOrder("bday"),
                db.QueryOrder("age", db.SortOrder.Descending),
            )

        sorts every Person in order of their birthday, starting with January 1.
        People with the same birthday are sorted by age, oldest to youngest.


        ``order()`` may be called multiple times. Each call resets the sort order
        from scratch.

        If an inequality filter exists in this Query it must be the first property
        passed to ``order()``. Any number of sort orders may be used after the
        inequality filter property. Without inequality filters, any number of
        filters with different orders may be specified.

        Entities with multiple values for an order property are sorted by their
        lowest value.

        Note that a sort order implies an existence filter! In other words,
        Entities without the sort order property are filtered out, and *not*
        included in the query results.

        If the sort order property has different types in different entities -
        e.g. if bob["id"] is an int and fred["id"] is a string - the entities will be
        grouped first by the property type, then sorted within type. No attempt is
        made to compare property values across types.


        :param orderings: The properties to sort by, in sort order. Each argument may be a
            :class:`QueryOrder`, a ``(name, direction)`` tuple, or a plain ``str`` (implies
            ``SortOrder.Ascending``).
        :returns: Returns the query itself for chaining.
        """
        if self.queries is None:
            # This Query is unsatisfiable - don't try to bother
            return self

        # Check for correct order subscript
        orders = []
        for order in orderings:
            if isinstance(order, str):
                order = QueryOrder(order)
            elif isinstance(order, QueryOrder):
                pass
            elif (
                isinstance(order, (tuple, list)) and
                len(order) == 2 and
                isinstance(order[0], str) and isinstance(order[1], SortOrder)
            ):
                order = QueryOrder(order[0], order[1])
            else:
                raise TypeError(
                    f"Invalid ordering {order!r}, expected a (str, SortOrder) tuple or QueryOrder."
                    f' Try: `QueryOrder("{order}")`'
                )
            orders.append(order)

        if self._orderHook is not None:
            try:
                orders = self._orderHook(self, orders)
            except RuntimeError:
                self.queries = None
                return self
            if orders is None:
                return self

        if isinstance(self.queries, list):
            for query in self.queries:
                query.orders = list(orders)
        else:
            self.queries.orders = list(orders)

        return self

    def setCursor(self, startCursor: str, endCursor: t.Optional[str] = None) -> t.Self:
        """
        Sets the start and optionally end cursor for this query.

        The result set will only include results between these cursors.
        The cursor is generated by an earlier query with exactly the same configuration.

        It's safe to use client-supplied cursors, a cursor can't be abused to access entities
        which don't match the current filters.

        *startCursor* and *endCursor* are interchangeably the same format — a value package issued by
        ``getCursor()`` together with the query hash (``_cursor_hash``); whether it acts as the lower or the
        upper bound is decided solely by the parameter it is passed to. A cursor whose hash does not match the
        current query is rejected with a ``ValueError``.

        For multi queries (SpatialBone/RandomSliceBone) that check deliberately stays off: a single sub query,
        whose filters differ from the others (one value of an IN filter each, say), would never carry the same
        hash as the one ``getCursor`` took it from. That is a documented limit, not an accidental gap.

        :param startCursor: The start cursor for this query.
        :param endCursor: The end cursor for this query.
        :returns: Returns the query itself for chaining.
        """
        def _decode(token: str) -> tuple[dict, str]:
            payload = vjson.loads(base64.urlsafe_b64decode(token.encode("ASCII")).decode("ASCII"))
            return payload["after"], payload["q"]

        after = after_hash = before = before_hash = None
        if startCursor:
            after, after_hash = _decode(startCursor)
        if endCursor:
            before, before_hash = _decode(endCursor)

        if isinstance(self.queries, list):
            for query in self.queries:
                assert isinstance(query, QueryDefinition)
                if startCursor:
                    query.startCursor = after
                if endCursor:
                    query.endCursor = before
        else:
            assert isinstance(self.queries, QueryDefinition)
            if startCursor:
                if after_hash != _cursor_hash(self.queries):
                    raise ValueError("This cursor was issued for a different query")
                self.queries.startCursor = after
            if endCursor:
                if before_hash != _cursor_hash(self.queries):
                    raise ValueError("This cursor was issued for a different query")
                self.queries.endCursor = before
        return self

    def limit(self, limit: int) -> t.Self:
        """
        Sets the query limit to *limit* entities in the result.

        :param limit: The maximum number of entities per batch.
        :returns: Returns the query itself for chaining.
        """
        if isinstance(self.queries, QueryDefinition):
            self.queries.limit = limit
        elif isinstance(self.queries, list):
            for query in self.queries:
                query.limit = limit

        return self

    def distinctOn(self, keyList: t.List[str]) -> t.Self:
        """
        Ensure only entities with distinct values on the fields listed are returned.
        This will implicitly override your SortOrder as all fields listed in keyList have to be sorted first.
        """
        if isinstance(self.queries, QueryDefinition):
            self.queries.distinct = keyList
        elif isinstance(self.queries, list):
            for query in self.queries:
                query.distinct = keyList
        return self

    def getCursor(self) -> t.Optional[str]:
        """
        Get a valid cursor from the last run of this query.

        The source of this cursor varies depending on what the last call was:
        - :meth:`run`: A cursor that points immediately behind the
            last result pulled off the returned iterator.
        - :meth:`get`: A cursor that points immediately behind the
            last result in the returned list.

        :returns: A cursor that can be used in subsequent query requests or None if that query does not support
            cursors or there are no more elements to fetch
        """
        if isinstance(self.queries, QueryDefinition):
            q = self.queries
        elif isinstance(self.queries, list):
            for query in self.queries:
                if query.currentCursor:
                    q = query
                    break
            else:
                q = self.queries[0]
        # currentCursor is the value package of the last row seen (a dict), not an offset string — the pair
        # of value package and query hash forms the public cursor that setCursor() takes apart again.
        if not q.currentCursor:
            return None
        payload = {"after": q.currentCursor, "q": _cursor_hash(q)}
        return base64.urlsafe_b64encode(vjson.dumps(payload).encode("ASCII")).decode("ASCII")

    def get_orders(self) -> t.List[QueryOrder] | None:
        """
        Get the orders from this query.

        :returns: The orders form this query as a list if there is no orders set it returns None
        """
        q = self.queries

        if isinstance(q, (list, tuple)):
            q = q[0]

        if not isinstance(q, QueryDefinition):
            raise ValueError(
                f"self.queries can only be a 'QueryDefinition' or a list of, but found {self.queries!r}"
            )

        return q.orders or None

    # TODO We need this the kind is already public.
    def getKind(self) -> str:
        """
        :returns: the *current* kind of this query.
            This may not be the kind this query has been constructed with
            as relational bones may rewrite this.
        """
        return self.kind

    def _run_single_filter_query(self, query: QueryDefinition, limit: int, keys_only: bool) -> list[dict] | list[str]:
        """
        Internal helper function that runs a single query definition on the datastore and returns a list of
        entities found.
        :param query: The querydefinition (filters, orders, distinct etc.) to run against the datastore
        :param limit: How many results should at most be returned
        :return: The first *limit* entities (or, if *keys_only*, their ``_id`` strings) that match this query
        """
        return run_single_filter(query, limit, keys_only)

    def _merge_multi_query_results(self, input_result: list[list[dict]]) -> list[dict]:
        """
        Merge the lists of entries into a single list; removing duplicates and restoring sort-order
        :param input_result: Nested Lists of Entries returned by each individual query run
        :return: Sorted & deduplicated list of entries
        """
        seen_keys = set()
        res = []
        for subList in input_result:
            for entry in subList:
                key = entry["_id"]
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                res.append(entry)
        # FIXME: What about filters that mix different inequality filters?
        # Currently, we'll now simply ignore any implicit sortorder.
        return self._resort_result(res, {}, self.queries[0].orders)

    def _resort_result(
        self,
        entities: list[dict],
        filters: dict[str, VALUE_TYPES],
        orders: t.List[QueryOrder],
    ) -> list[dict]:
        """
        Internal helper that takes a (deduplicated) list of entities that has been fetched from different internal
        queries (e.g. from SpatialBone or RandomSliceBone custom multi-queries) and resorts the list so it matches
        the query again. Regular IN/!= filters no longer use this path — they are handled natively by the Datastore.

        :param entities: t.List of entities to resort
        :param filters: The filter used in the query (used to determine implicit sort order by an inequality filter)
        :param orders: The sort-orders to apply
        :return: The sorted list
        """

        def getVal(src: dict, fieldVars: str | tuple[str], direction: SortOrder) -> t.Any:
            # Descent into the target until we reach the property we're looking for
            if isinstance(fieldVars, tuple):
                for fv in fieldVars:
                    if fv not in src:
                        return None
                    src = src[fv]
            else:
                if fieldVars not in src:
                    return (str(type(None)), 0)
                src = src[fieldVars]
            # Lists are handled differently, here the smallest or largest value determines it's position in the result
            if isinstance(src, list) and len(src):
                try:
                    src.sort()
                except TypeError:
                    # It's a list of dicts or the like for which no useful sort-order is specified
                    pass
                if direction == SortOrder.Ascending:
                    src = src[0]
                else:
                    src = src[-1]
            # We must return this tuple because inter-type comparison isn't possible in Python3 anymore
            return str(type(src)), src if src is not None else 0

        # Check if we have an inequality filter which implies a sortorder
        ineqFilter = None
        for k, _ in filters.items():
            end = k[-2:]
            if "<" in end or ">" in end:
                ineqFilter = k.split(" ")[0]
                break
        if ineqFilter and (not orders or not orders[0].name == ineqFilter):
            orders = [QueryOrder(ineqFilter)] + (orders or [])

        # ``_to_mongo_sort`` always appends ``_id`` as the last, unique sort criterion. This client side merge
        # (the SpatialBone/RandomSliceBone multi query) has to do the same, or equal sort values would be left
        # to the input order and the stability of Python's sort, inconsistent with the cursor the same query
        # issues.
        if not any(o.name == "_id" for o in orders):
            last_dir = orders[-1].order if orders else SortOrder.Ascending
            orders = list(orders) + [QueryOrder("_id", last_dir)]

        for orderField, direction in orders[::-1]:
            # ``_id`` (KEY_SPECIAL_PROPERTY) needs no special case here: it is an ordinary field of the
            # document, which ``getVal`` reads through the same ``src[fieldVars]`` access as any other field.
            try:
                entities.sort(key=functools.partial(getVal, fieldVars=orderField, direction=direction),
                              reverse=direction == SortOrder.Descending)
            except TypeError:
                # We hit some incomparable types
                pass
        return entities

    def _fixKind(self, resultList: list[dict]) -> list[dict]:
        """
        Jump to parentKind if necessary (used in relations)
        """
        resultList = list(resultList)

        # A relational query runs against "viur-relations" but has to return the source records. The source
        # used to be the ancestor of the key; MongoDB has no hierarchy, so it is read from the "src" subdocument
        # carried along instead.
        #
        # With keys_only the result list holds bare _id strings (run_single_filter converts them already) and
        # there is no "src" field that could carry the resolution — the isinstance check keeps that case out
        # before .get() would fail on a str.
        if (self.origKind and resultList
                and isinstance(resultList[0], dict)
                and resultList[0].get("viur_src_kind") == self.origKind):
            source_ids = list(dict.fromkeys(
                entry["src"]["_id"] for entry in resultList if entry.get("src")
            ))
            return get(self.origKind, source_ids)

        return resultList

    def run(self, limit: int = -1, keys_only: bool = False) -> list[dict] | list[str]:
        """
        Run this query.

        It is more efficient to use *limit* if the number of results is known.

        If queried data is wanted as instances of Skeletons, :meth:`fetch`
        should be used.

        :param limit: Limits the query to the defined maximum entities.
        :param keys_only: If True, only return the ``_id`` of each entity, as a string.

        :returns: The list of found entities (or, if *keys_only*, their ``_id`` strings)

        :raises: :exc:`BadFilterError` if a filter string is invalid
        :raises: :exc:`BadValueError` if a filter value is invalid.
        """
        if self.queries is None:
            if conf.debug.trace_queries:
                logging.debug(f"Query on {self.kind} aborted as being not satisfiable")
            return []

        if self._fulltextQueryString:
            if utils.is_in_transaction():
                raise ValueError("Can't run fulltextSearch inside transactions!")  # InvalidStateError FIXME!
            if keys_only:
                raise ValueError("Can't run fulltextSearch with keysOnly!")
            qryStr = self._fulltextQueryString
            self._fulltextQueryString = None  # Reset, so the adapter can still work with this query
            res = self.srcSkel.customDatabaseAdapter.fulltextSearch(qryStr, self)

            if not self.srcSkel.customDatabaseAdapter.fulltextSearchGuaranteesQueryConstrains:
                # Search might yield results that are not included in the listfilter
                if isinstance(self.queries, QueryDefinition):  # Just one
                    res = [x for x in res if _entryMatchesQuery(x, self.queries.filters, self.queries.or_filters)]
                else:  # Multi-Query, must match at least one
                    res = [x for x in res if
                           any([_entryMatchesQuery(x, y.filters, y.or_filters) for y in self.queries])]

        elif isinstance(self.queries, list):
            limit = limit if limit >= 0 else self.queries[0].limit

            # We have more than one query to run
            if self._calculateInternalMultiQueryLimit:
                limit = self._calculateInternalMultiQueryLimit(self, limit)

            res = []
            # We run all queries first (preventing multiple round-trips to the server)
            for singleQuery in self.queries:
                res.append(self._run_single_filter_query(singleQuery, limit, keys_only))

            # Wait for the actual results to arrive and convert the protobuffs to Entries
            res = [self._fixKind(x) for x in res]
            if self._customMultiQueryMerge:
                # We have a custom merge function, use that
                res = self._customMultiQueryMerge(self, res, limit)
            else:
                # We must merge (and sort) the results ourself
                res = self._merge_multi_query_results(res)

        else:  # We have just one single query
            res = self._fixKind(self._run_single_filter_query(
                self.queries,
                limit if limit >= 0 else self.queries.limit,
                keys_only
            ))

        if res:
            # run_single_filter already returns bare _id strings for keys_only, so nothing has to be
            # converted here (the old Datastore path passed entities/keys through).
            self._lastEntry = res[-1]

        return res

    def count(self, up_to: int = 2 ** 63 - 1) -> int:
        """
            The count operation cost one entity read for up to 1,000 index entries matched
            (https://cloud.google.com/datastore/docs/aggregation-queries#pricing)
            :param up_to can be sigend int 64 bit (max positive 2^31-1)

            :returns: Count entries for this query.
        """
        if self.queries is None:
            if conf.debug.trace_queries:
                logging.debug(f"Query on {self.kind} aborted as being not satisfiable")
            return -1
        elif isinstance(self.queries, list):
            raise ValueError("No count on Multiqueries")
        else:
            qd = self.queries
            return count(qd.kind, _to_mongo_filter(qd.filters, qd.or_filters), up_to)

    def fetch(self, limit: int = -1) -> "SkelList":
        """
        Run this query and fetch results as :class:`core.skeleton.SkelList`.

        This function is similar to :meth:`run`, but returns a
        :class:`core.skeleton.SkelList` instance instead of plain documents.

        :warning: The query must be limited!

        If queried data is wanted as plain documents (``dict``), :meth:`run`
        should be used.

        :param limit: Limits the query to the defined maximum entities.

        :raises: :exc:`BadFilterError` if a filter string is invalid
        :raises: :exc:`BadValueError` if a filter value is invalid.
        """
        from viur.core.skeleton import SkelList, SkeletonInstance

        if self.srcSkel is None:
            raise NotImplementedError("This query has not been created using skel.all()")

        res = SkelList(self.srcSkel)

        # FIXME: Why is this not like in ViUR2?
        for entity in self.run(limit):
            skel_instance = SkeletonInstance(self.srcSkel.skeletonCls, bone_map=self.srcSkel.boneMap)
            skel_instance.dbEntity = entity
            res.append(skel_instance)

        res.getCursor = lambda: self.getCursor()
        res.get_orders = lambda: self.get_orders()

        return res

    def iter(self, keys_only=False) -> t.Iterator[dict] | t.Iterator[str]:
        """
        Run this query and return an iterator for the results.

        The advantage of this function is, that it allows for iterating
        over a large result-set, as it hasn't have to be pulled in advance
        from the datastore.

        This function intentionally ignores a limit set by :meth:`limit`.

        :warning: If iterating over a large result set, make sure the query supports cursors. \
        Otherwise, it might not return all results as the AppEngine doesn't maintain the view \
        for a query for more than ~30 seconds.
        """
        if self.queries is None:  # Noting to pull here
            return
        elif isinstance(self.queries, list):
            raise ValueError("No iter on Multiqueries")
        while True:
            # run_single_filter already yields bare _id strings when keys_only is set.
            batch = self._run_single_filter_query(self.queries, 100, keys_only)
            yield from batch
            if not self.queries.currentCursor:  # We reached the end of that query
                break
            self.queries.startCursor = self.queries.currentCursor

    def iter_skel(self) -> t.Iterator["SkeletonInstance"]:
        """
        Run this query and return an iterator yielding :class:`core.skeleton.SkeletonInstance`.

        This function is to :meth:`iter` what :meth:`fetch` is to :meth:`run`: it allows for
        iterating over a large result-set without pulling it from the datastore in advance,
        but yields SkeletonInstances instead of Entities.

        It's only possible to use this function if this query has been created using
        :func:`core.skeleton.Skeleton.all`.

        Every result is a separate SkeletonInstance which shares the bone-map of the
        source-skeleton, therefore collecting the results in a list or writing them
        within the loop behaves as expected.

        This function intentionally ignores a limit set by :meth:`limit`.

        :warning: If iterating over a large result set, make sure the query supports cursors. \
        Otherwise, it might not return all results as the AppEngine doesn't maintain the view \
        for a query for more than ~30 seconds.

        :raises NotImplementedError: If this query has not been created using skel.all().
        :raises ValueError: If this is a multi-query, which cannot be iterated.
        """
        if self.srcSkel is None:
            raise NotImplementedError("This query has not been created using skel.all()")
        elif isinstance(self.queries, list):
            raise ValueError("No iter_skel on Multiqueries")

        from viur.core.skeleton import SkeletonInstance

        # Wrapped in an inner generator, so the checks above are raised on call and not on first next()
        def _iterate() -> t.Iterator["SkeletonInstance"]:
            for entity in self.iter():
                skel_instance = SkeletonInstance(self.srcSkel.skeletonCls, bone_map=self.srcSkel.boneMap)
                skel_instance.dbEntity = entity
                yield skel_instance

        return _iterate()

    def getEntry(self) -> dict | None:
        """
        Returns only the first entity of the current query.

        :returns: The first entity on success, or None if the result-set is empty.
        """
        try:
            res = list(self.run(limit=1))[0]
            return res
        except (IndexError, TypeError):  # Empty result-set
            return None

    def getSkel(self) -> t.Optional["SkeletonInstance"]:
        """
        Returns a matching :class:`core.db.skeleton.Skeleton` instance for the
        current query.

        It's only possible to use this function if this query has been created using
        :func:`core.skeleton.Skeleton.all`.

        :returns: The Skeleton or None if the result-set is empty.
        """
        if self.srcSkel is None:
            raise NotImplementedError("This query has not been created using skel.all()")

        if not (res := self.getEntry()):
            return None
        self.srcSkel.setEntity(res)
        return self.srcSkel

    def clone(self) -> t.Self:
        """
        Returns a deep copy of the current query.

        :returns: The cloned query.
        """
        res = Query(self.getKind(), self.srcSkel)
        res.kind = self.kind
        res.queries = copy.deepcopy(self.queries)
        # res.filters = copy.deepcopy(self.filters)
        # res.orders = copy.deepcopy(self.orders)
        # res._limit = self._limit
        res._filterHook = self._filterHook
        res._orderHook = self._orderHook
        # FIXME: Why is this disabled ???
        # res._startCursor = self._startCursor
        # res._endCursor = self._endCursor
        res._customMultiQueryMerge = self._customMultiQueryMerge
        res._calculateInternalMultiQueryLimit = self._calculateInternalMultiQueryLimit
        res.customQueryInfo = self.customQueryInfo
        res.origKind = self.origKind
        res._fulltextQueryString = self._fulltextQueryString
        # res._distinct = self._distinct
        return res

    def keys_only(self, limit: int = -1) -> list[str]:
        return self.run(limit, True)

    def __repr__(self) -> str:
        return f"<db.Query on {self.kind} with queries {self.queries}>"
