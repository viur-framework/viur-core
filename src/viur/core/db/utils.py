import datetime
import typing as t

from pymongo.client_session import ClientSession

from viur.core import current
from . import objectid, transport
from .transport import get, put, run_in_transaction
from .types import current_db_access_log, KEY_SPECIAL_PROPERTY, SortOrder

_OPS: t.Final[dict[str, str]] = {
    "<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte", "IN": "$in", "NOT_IN": "$nin", "!=": "$ne",
}
"""viur comparison operator -> Mongo operator."""

_INEQUALITY_OPS: t.Final[frozenset[str]] = frozenset({"<", "<=", ">", ">="})


def is_in_transaction() -> bool:
    """Is a transaction running right now (a nested one included)?"""
    return transport._current_session.get() is not None


def get_or_insert(kind: str, _id: str, **defaults) -> dict:
    """
    Either creates a new document with the given ``kind``/``_id``, or returns the existing one.

    Its guaranteed that there is no race-condition here; it will never overwrite a
    previously created document. Extra keyword arguments passed to this function will be
    used to populate the document if it has to be created; otherwise they are ignored.

    :param kind: The kind the document lives in.
    :param _id: The ``_id`` which will be fetched or created.
    :returns: Returns the fetched or newly created document.
    """

    def txn(kind, _id, defaults):
        obj = get(kind, _id)
        if not obj:
            obj = {"_id": _id, **defaults}
            put(kind, obj)
        return obj

    if is_in_transaction():
        return txn(kind, _id, defaults)
    return run_in_transaction(txn, kind, _id, defaults)


def acquire_transaction_success_marker() -> str:
    """
        Generates a token that will be written to the datastore (under "viur-transactionmarker") if the transaction
        completes successfully. Currently only used by deferredTasks to check if the task should actually execute
        or if the transaction it was created in failed.

        :return: Name of the entry in viur-transactionmarker
    """
    session: ClientSession | None = transport._current_session.get()
    assert session, "acquire_transaction_success_marker cannot be called outside an transaction"
    marker = objectid.new_id()
    request_data = current.request_data.get()
    if not request_data.get("__viur-transactionmarker__"):
        put("viur-transactionmarker", {
            "_id": marker,
            "creationdate": datetime.datetime.now(datetime.timezone.utc),
        })
        request_data["__viur-transactionmarker__"] = True
    return marker


def start_data_access_log() -> set[str]:
    """
        Clears our internal access log (which keeps track of which entries have been accessed in the current
        request). The old set of accessed entries is returned so that it can be restored with
        :func:`end_data_access_log` in case of nested caching. You must call end_data_access_log afterwards, otherwise
        we'll continue to log all entries accessed in subsequent request on the same thread!
        :return: t.Set of old accessed entries
    """
    old = current_db_access_log.get(set())
    current_db_access_log.set(set())
    return old


def end_data_access_log(
    outer_access_log: set[str] | None = None,
) -> set[str] | None:
    """
       Retrieves the set of entries accessed so far.

       To clean up and restart the log, call :func:`start_data_access_log`.

       If you called :func:`start_data_access_log` before, you can re-apply the old log using
       the outer_access_log param. Otherwise, it will disable the access log.

       :param outer_access_log: State of your log returned by :func:`start_data_access_log`
       :return: t.Set of entries accessed
       """
    res = current_db_access_log.get()
    if isinstance(outer_access_log, set):
        current_db_access_log.set((outer_access_log or set()).union(res))
    else:
        current_db_access_log.set(None)
    return res


def reject_legacy_key(name: str) -> None:
    """Refuse the Datastore pseudo name ``__key__`` in a filter or an order with a ``ValueError``."""
    # A document has no ``__key__`` field, so a query naming it would silently match nothing.
    if name == "__key__" or name.endswith(".__key__"):
        replacement = name.replace("__key__", KEY_SPECIAL_PROPERTY)
        raise ValueError(f"{name!r}: __key__ is gone — use {replacement!r} "
                         f"(db.KEY_SPECIAL_PROPERTY) instead")


def to_mongo_filter(filters: dict, or_filters: list) -> dict:
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
        groups.append({"$or": [to_mongo_filter({k: v}, []) for k, v in group]})
    if groups:
        out = {"$and": [out, *groups]} if out else ({"$and": groups} if len(groups) > 1 else groups[0])
        if isinstance(out, dict) and "$and" in out and len(out["$and"]) == 1:
            out = out["$and"][0]
    return out


def _split(key: str) -> tuple[str, str]:
    """Split a viur filter key (``"field op"``) into field and operator."""
    # ``Query.filter`` always stores the key as f"{field} {op}" and a field itself holds no space, so
    # ``rpartition`` splits at the actual operator.
    name, _, op = key.rpartition(" ")
    reject_legacy_key(name)
    return name, (op or "=")


def implicit_orders(filters: dict) -> list[tuple[str, SortOrder]]:
    """The order of a query without ``order``: ascending by its inequality field, if there is exactly one.

    Several operators on the same field count as one, IN/!= are no range filters, and ``or_filters`` never count.
    Only with this order an index ``(equality fields…, field, _id)`` can carry the sort elision.
    """
    fields = {field for field, op in (_split(k) for k in filters) if op in _INEQUALITY_OPS}
    return [(fields.pop(), SortOrder.Ascending)] if len(fields) == 1 else []


def to_mongo_sort(orders) -> list[tuple[str, int]]:
    """The Mongo order, with ``_id`` appended as the last criterion.

    Without an explicit criterion the order is not deterministic, and keyset pagination needs a unique
    tiebreaker. ``Inverted*`` flips the fetch direction; ``run_single_filter`` flips the result back, so it
    appears in display order.
    """
    out = []
    for name, order in orders:
        reject_legacy_key(name)
        desc = order in (SortOrder.Descending, SortOrder.InvertedAscending)
        out.append((name, -1 if desc else 1))
    if not any(f == "_id" for f, _ in out):
        last_dir = out[-1][1] if out else 1
        out.append(("_id", last_dir))
    return out


def after_condition(sort: list[tuple[str, int]], after: dict, *, inclusive: bool = False) -> dict:
    """The keyset continuation ``(a, b, ..., _id) > (va, vb, ..., vid)``, as an ``$or`` chain per sort field.

    *sort* is already the Mongo order from ``to_mongo_sort``, for an ``Inverted*`` order therefore the
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


def before_condition(sort: list[tuple[str, int]], before: dict) -> dict:
    """The upper keyset bound for ``endCursor``: :func:`after_condition` with every direction flipped.

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


def dotted_get(doc: dict, path: str) -> t.Any:
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
