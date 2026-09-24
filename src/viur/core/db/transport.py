"""
MongoDB transport layer: the process-wide client, the session context and the document-based CRUD functions.

A kind is a collection of the same name and a key is the ``_id`` of a document — any non-empty ``str``.
:func:`put` generates an ObjectId hex when the caller supplies none, but viur also writes deterministic business
keys (the ``viur-conf`` singleton, the locks of unique constraints, ratelimit counters); there the uniqueness of
``_id`` carries the atomicity, which a separate field plus a query could not.
"""
from __future__ import annotations

import contextvars
import datetime
import logging
import threading
import time
import typing as t

import pymongo
from pymongo import InsertOne, MongoClient, ReplaceOne
from pymongo.auth_oidc import OIDCCallback, OIDCCallbackContext, OIDCCallbackResult
from pymongo.client_session import ClientSession
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError

from viur.core.config import conf
from . import cache, objectid
from .types import QueryDefinition, SortOrder

logger = logging.getLogger(__name__)

_DEFAULT_SERVER_SELECTION_TIMEOUT_MS: t.Final[int] = 5000
_DEFAULT_CONNECT_TIMEOUT_MS: t.Final[int] = 5000
"""Bounds for an unreachable database, applied unless ``conf.db.uri`` sets them: pymongo's own defaults (30 s for
server selection, 20 s per connection attempt) would block every request thread that long instead of failing
fast."""

_mongo_client: MongoClient | None = None
_mongo_lock = threading.Lock()
"""Guards the one-time construction of ``_mongo_client``. A ``MongoClient`` is built to be shared across
threads afterwards; only its creation needs the lock, otherwise two concurrent first accesses build two
connection pools."""

_current_session: contextvars.ContextVar[ClientSession | None] = contextvars.ContextVar(
    "viur_db_session", default=None
)
"""The running transaction, separate per thread and per async task — a ``ClientSession``, unlike the
``MongoClient``, must not be shared."""

_transaction_outdated: contextvars.ContextVar[list[tuple[str, str]] | None] = contextvars.ContextVar(
    "viur_db_transaction_outdated", default=None
)
"""The ``(kind, _id)`` pairs the transaction running in this context has written or deleted; their cache entries
are dropped once the transaction is over, as the cache cannot be updated while it may still roll back."""

_elision_disabled: set[tuple[str, str]] = set()
_elision_lock = threading.Lock()
"""Guards ``_elision_disabled``, the ``(kind, index name)`` pairs whose sort elision is off for the rest of the
process (see :func:`_find`); held only around the set operation, never around I/O."""

Document: t.TypeAlias = dict[str, t.Any]
"""A record as the driver returns it: a dict carrying an ``_id``."""


def get_collection(kind: str) -> Collection:
    """The collection belonging to a kind — one to one, under the same name."""
    return _mongo()[conf.db.name][kind]


def _mongo() -> MongoClient:
    """The shared client, built on first access, so importing viur.core needs no database credentials."""
    global _mongo_client
    if _mongo_client is None:
        with _mongo_lock:
            if _mongo_client is None:  # a second thread was faster
                # Only set what the URI does not carry itself — ``conf.db.uri`` wins, it is the explicit wish of
                # an operator. ``parse_uri`` normalizes the case of the option names, so testing the canonical
                # name with ``in`` is enough.
                options = pymongo.uri_parser.parse_uri(conf.db.uri).get("options", {})
                kwargs = {}
                if "serverSelectionTimeoutMS" not in options:
                    kwargs["serverSelectionTimeoutMS"] = _DEFAULT_SERVER_SELECTION_TIMEOUT_MS
                if "connectTimeoutMS" not in options:
                    kwargs["connectTimeoutMS"] = _DEFAULT_CONNECT_TIMEOUT_MS
                if "tz_aware" not in options:
                    # pymongo returns dates naive by default, while the whole core compares against the aware
                    # utils.utcNow() — a naive date from the database would raise a TypeError.
                    kwargs["tz_aware"] = True
                if (options.get("authMechanism") == "MONGODB-OIDC"
                        and "ENVIRONMENT" not in (options.get("authMechanismProperties") or {})):
                    # Firestore Enterprise: a token from the application default credentials, locally as well as
                    # in production (see _GoogleAdcOidc). If the URI names an ENVIRONMENT itself, the driver
                    # mechanism stays untouched.
                    kwargs["authMechanismProperties"] = {"OIDC_CALLBACK": _GoogleAdcOidc()}
                client = MongoClient(conf.db.uri, **kwargs)
                if client.options.retry_writes:
                    raise RuntimeError(
                        "conf.db.uri must set retryWrites=false: "
                        "Firestore Enterprise does not support retryable writes"
                    )
                _mongo_client = client
    return _mongo_client


class _GoogleAdcOidc(OIDCCallback):
    """Hands the driver a Google access token taken from the application default credentials.

    Firestore Enterprise authenticates via ``MONGODB-OIDC``. The variant named in its documentation,
    ``authMechanismProperties=ENVIRONMENT:gcp``, asks the GCE metadata server, which exists on App Engine but
    not on a development machine. Application default credentials cover both: ``gcloud auth
    application-default login`` locally, the service identity in production. ``_mongo()`` therefore attaches
    this callback as soon as the URI asks for ``MONGODB-OIDC`` without naming an ``ENVIRONMENT`` itself.

    No module state: ``google.auth.default()`` is read per call, and the driver only calls back when it needs a
    new token.
    """

    def fetch(self, context: OIDCCallbackContext) -> OIDCCallbackResult:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())
        expires_in = None
        if credentials.expiry is not None:
            # google-auth reports the expiry as a naive UTC time
            remaining = credentials.expiry - datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            expires_in = max(remaining.total_seconds(), 0)
        return OIDCCallbackResult(access_token=credentials.token, expires_in_seconds=expires_in)


def get(kind: str, ids: str | list[str] | set[str] | tuple[str, ...]) -> Document | list[Document] | None:
    """Load one document (or several) from *kind*.

    A single id yields the document or ``None``, a collection of ids yields the documents found in request
    order, leaving missing ones out. Several ids are recognized by the collection type, not by iterability — a
    ``str`` is iterable itself.

    The memcache serves what it holds; only the remaining ids go to MongoDB, in a single ``$in`` batch, and
    their answer warms the cache. Inside a transaction the cache returns nothing, so reads are always fresh.

    :param kind: The kind to read from.
    :param ids: A single ``_id``, or a list/set/tuple of them.
    :return: The document, ``None``, or the list of documents found.
    """
    is_multiple = isinstance(ids, (list, set, tuple))
    id_list = list(ids) if is_multiple else [ids]
    for _id in id_list:
        _check_id(_id)

    if not id_list:  # like delete(): an empty request needs no roundtrip
        return []

    found = {doc["_id"]: doc for doc in cache.get(kind, id_list)}

    # Only the ids the cache did not hold go to MongoDB, and their answer warms the cache.
    missing = [_id for _id in id_list if _id not in found]
    if missing:
        fetched = list(get_collection(kind).find({"_id": {"$in": missing}}, session=_current_session.get()))
        if fetched:
            cache.put(kind, fetched)
        for doc in fetched:
            found[doc["_id"]] = doc

    if not is_multiple:
        return found.get(id_list[0])
    return [found[_id] for _id in id_list if _id in found]


def _check_id(_id: t.Any) -> None:
    """Reject anything but a non-empty ``str`` — on deterministic keys see the module docstring."""
    if not isinstance(_id, str) or not _id:
        raise ValueError(f"_id must be a non-empty str, got {_id!r}")


def put(kind: str, docs: Document | list[Document]) -> Document | list[Document]:
    """Write one document (or several) to *kind*.

    A missing ``_id`` is generated and written into the given dict, so the caller knows the id of the record
    just written. The cache is warmed only after the write succeeded, so a value never persisted is never cached.

    :param kind: The kind to write to.
    :param docs: A single document, or a list of them.
    :return: The very same document (or list of documents), ``_id`` filled in.
    """
    is_multiple = isinstance(docs, list)
    doc_list = docs if is_multiple else [docs]
    for doc in doc_list:
        if not (_id := doc.get("_id")):
            doc["_id"] = objectid.new_id()
        else:
            _check_id(_id)

    col = get_collection(kind)
    session = _current_session.get()
    if len(doc_list) == 1:
        # For a single document the lookup of _put_many does not pay off.
        col.replace_one({"_id": doc_list[0]["_id"]}, doc_list[0], upsert=True, session=session)
    else:
        _put_many(col, doc_list, session)

    # Inside a transaction cache.put() does nothing, run_in_transaction() drops the old entries afterwards.
    _mark_as_outdated(kind, [doc["_id"] for doc in doc_list])
    cache.put(kind, docs)
    return docs


def _put_many(col: Collection, doc_list: list[Document], session: ClientSession | None) -> None:
    """Insert what is new and replace what exists, instead of upserting everything.

    An upsert that *creates* is the expensive path on Firestore Enterprise (100 new documents: 1014 ms, against
    49 ms for plain inserts), so one lookup of the existing ids pays for itself.

    Both bulks run ``ordered=False`` so the server may work in parallel. A race between the lookup and the
    insert — another thread creating the same ``_id`` — shows up as ``E11000`` in the unordered bulk, which
    writes the rest anyway; the affected documents are replaced instead. Any other error stays an error.

    :param col: The collection to write to.
    :param doc_list: The documents to write, each one carrying an ``_id``.
    :param session: The session of a running transaction, or ``None``.
    """
    ids = [d["_id"] for d in doc_list]
    existing = {d["_id"] for d in col.find({"_id": {"$in": ids}}, {"_id": 1}, session=session)}
    inserts = [d for d in doc_list if d["_id"] not in existing]
    replaces = [d for d in doc_list if d["_id"] in existing]

    if inserts:
        try:
            col.bulk_write([InsertOne(d) for d in inserts], ordered=False, session=session)
        except BulkWriteError as exc:
            errors = exc.details.get("writeErrors", [])
            if not errors or any(e.get("code") != 11000 for e in errors):
                raise
            replaces += [inserts[e["index"]] for e in errors]

    if replaces:
        col.bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in replaces],
                       ordered=False, session=session)


def _mark_as_outdated(kind: str, ids: list[str]) -> None:
    """Record documents whose cache entry the transaction running in this context outdates."""
    if (outdated := _transaction_outdated.get()) is not None:
        outdated.extend((kind, _id) for _id in ids)


def delete(kind: str, ids: str | list[str] | set[str] | tuple[str, ...]) -> None:
    """Delete documents from *kind*; unknown ids are not an error.

    The cache entry is dropped before the deletion itself: an entry that survived a failed delete would be
    served until it expires.
    """
    id_list = list(ids) if isinstance(ids, (list, set, tuple)) else [ids]
    if not id_list:
        return
    # Dropped again once a surrounding transaction is over: until then a concurrent read could bring the
    # still committed value back into the cache.
    _mark_as_outdated(kind, id_list)
    cache.delete(kind, id_list)
    get_collection(kind).delete_many({"_id": {"$in": id_list}}, session=_current_session.get())


def count(kind: str, flt: dict | None = None, up_to: int | None = None) -> int:
    """Count the documents in *kind*, optionally narrowed by a Mongo filter and cut short by *up_to*."""
    # ``limit`` makes MongoDB stop counting once *up_to* hits are found, instead of counting through the whole
    # (possibly much larger) result set — the cost bound ``Query.count(up_to=...)`` has always promised.
    kwargs = {"limit": up_to} if up_to else {}
    return get_collection(kind).count_documents(flt or {}, session=_current_session.get(), **kwargs)


def run_in_transaction(func: t.Callable, *args, **kwargs) -> t.Any:
    """Run *func* in a transaction — either all of its writes are applied or none of them.

    If a transaction is already running, *func* runs inside it without a second one being opened. A transaction
    conflict is retried three times with an exponential backoff, every other error propagates. A read inside the
    transaction is not guaranteed to see a value written earlier in it — keep such a value in a local variable.

    :param func: The callable to run; further arguments are passed on to it.
    :return: Whatever *func* returned.
    :raises RuntimeError: When the retries are exhausted.
    """
    if _current_session.get() is not None:
        # Nested call: the outermost one drops the outdated cache entries.
        return func(*args, **kwargs)

    outdated_token = _transaction_outdated.set([])
    try:
        for i in range(3):
            try:
                with _mongo().start_session() as session:
                    token = _current_session.set(session)
                    try:
                        with session.start_transaction():
                            res = func(*args, **kwargs)
                        break
                    finally:
                        _current_session.reset(token)

            except pymongo.errors.PyMongoError as exc:
                # A retryable conflict: MongoDB sets the label, Firestore reports code 112 ("Aborted").
                if not (
                    exc.has_error_label("TransientTransactionError")
                    or (isinstance(exc, pymongo.errors.OperationFailure) and exc.code == 112)
                ):
                    raise
                logger.error(f"Transaction failed with a conflict, trying again in {2 ** i} seconds")
                time.sleep(2 ** i)
                continue
        else:
            raise RuntimeError("Maximum transaction retries exceeded")

    finally:
        # Also after a failed transaction: an attempt may have written before the conflict, and one
        # invalidation too many only costs a lookup.
        outdated = _transaction_outdated.get()
        _transaction_outdated.reset(outdated_token)
        by_kind: dict[str, list[str]] = {}
        for kind, _id in outdated:
            by_kind.setdefault(kind, []).append(_id)
        for kind, ids in by_kind.items():
            cache.delete(kind, ids)

    return res


def run_single_filter(query: QueryDefinition, limit: int, keys_only: bool) -> list[dict | str]:
    """Run a single ``QueryDefinition`` against MongoDB and return the hits.

    *query* is the ``QueryDefinition`` itself, not the ``Query`` — that is how ``Query._run_single_filter_query``
    calls, and for a multi-query (``SpatialBone``, ``RandomSliceBone``) exactly one of the definitions in
    ``Query.queries`` arrives here at a time.

    Cursors are keyset pagination: ``startCursor``/``endCursor`` carry the sort values of a row already seen and
    become a lower or upper bound ``$and``-ed onto the filter, unambiguous because ``utils.to_mongo_sort`` always
    appends ``_id``. An ``Inverted*`` query reads its start cursor inclusively and flips the result into display
    order afterwards.

    :param query: The single query definition to run.
    :param limit: The maximum number of documents to return.
    :param keys_only: Return only the ``_id`` of each hit instead of the whole document.
    :return: The documents found, or their ``_id``s when *keys_only* is set.
    """
    # imported here, db.utils itself imports this module
    from . import indexes
    from .utils import (
        after_condition, before_condition, dotted_get, implicit_orders, to_mongo_filter, to_mongo_sort,
    )

    flt = to_mongo_filter(query.filters, query.or_filters)
    eq_fields = indexes.equality_fields(flt)
    orders = query.orders or implicit_orders(query.filters or {})
    # A limit-1 lookup without any order (neither explicit nor implicit), without a cursor and without distinct
    # sends no sort(): the scan stops at the first hit instead of loading and sorting every hit.
    lookup = limit == 1 and not orders and not query.startCursor and not query.endCursor and not query.distinct
    sort = [] if lookup else to_mongo_sort(orders)
    inverted = any(
        order in (SortOrder.InvertedAscending, SortOrder.InvertedDescending)
        for _, order in (query.orders or [])
    )

    # Keyset continuation: an Inverted* query reads its start cursor inclusively, a plain one exclusively.
    extra = []
    if query.startCursor:
        extra.append(after_condition(sort, query.startCursor, inclusive=inverted))
    if query.endCursor:
        extra.append(before_condition(sort, query.endCursor))
    if extra:
        flt = {"$and": [flt, *extra]} if flt else ({"$and": extra} if len(extra) > 1 else extra[0])

    docs = _find(query.kind, flt, sort, query.distinct, limit, eq_fields=eq_fields)

    # The cursor of this run, and the flip back into display order.
    query.currentCursor = {field: dotted_get(docs[-1], field) for field, _ in sort} if docs and sort else None
    if inverted:
        docs.reverse()

    if keys_only:
        return [d["_id"] for d in docs]
    return docs


def _find(kind: str, flt: dict, sort: list[tuple[str, int]], distinct: list[str] | None, limit: int,
          *, eq_fields: frozenset[str] = frozenset()) -> list[dict]:
    """The read behind :func:`run_single_filter`: a plain ``find``, an elided sort, or an aggregation.

    *distinct* takes a completely different route through the driver (an aggregation instead of ``find``),
    while cursor, inversion and ``keys_only`` are the same for both — hence the split from
    :func:`run_single_filter`.

    With an explicit sort Firestore Enterprise fetches every index hit before applying the limit. So when an
    existing index already yields the requested order (``indexes.eligible``), ``sort()`` is dropped, that index
    is hinted instead and the order verified client-side (``order.is_sorted``). An unsorted result or a rejected
    hint falls back to the explicit sort and turns the elision off for that ``(kind, index)`` pair for the rest
    of the process. The elision never changes the result, only the way to it.

    :param kind: The kind to read from.
    :param flt: The Mongo filter.
    :param sort: The Mongo sort; empty for a lookup without any order.
    :param distinct: The fields to return one document per value combination of.
    :param limit: The maximum number of documents; ``0`` for no limit.
    :param eq_fields: The equality fields of *flt*, the prefix an index has to carry.
    :return: The documents found, in the order asked for.
    """
    from . import indexes, order

    collection = get_collection(kind)
    session = _current_session.get()
    if not distinct:
        if not sort:
            # Lookup without any order: the scan stops after `limit`, so neither sort() nor hint() is needed.
            # is_dev_server is checked first because `indexes.covers()` needs `listIndexes` — that must never
            # run on the production read path, only as a development aid.
            if conf.db.sort_elision and conf.instance.is_dev_server and not indexes.covers(kind, eq_fields):
                indexes.suggest(kind, eq_fields, [])
            cursor = collection.find(flt, session=session)
            if limit:
                cursor = cursor.limit(limit)
            return list(cursor)
        # An existing index that yields the order: hint it and leave sort() out.
        spec = indexes.eligible(kind, eq_fields, sort) if conf.db.sort_elision else None
        disabled = False
        if spec is not None:
            with _elision_lock:
                disabled = (kind, indexes.name(spec)) in _elision_disabled
        if spec is None or disabled:
            if conf.db.sort_elision and spec is None:
                indexes.suggest(kind, eq_fields, sort)
            return _find_sorted(collection, flt, sort, limit, session)
        try:
            cursor = collection.find(flt, session=session).hint(list(spec))
            if limit:
                cursor = cursor.limit(limit)
            docs = list(cursor)
        except pymongo.errors.OperationFailure as exc:
            # FIXME: a rejected hint arrives as a generic OperationFailure; narrowing it down would take a
            #        documented server error code, which neither MongoDB nor Firestore Enterprise promises.
            with _elision_lock:
                first = (kind, indexes.name(spec)) not in _elision_disabled
                _elision_disabled.add((kind, indexes.name(spec)))
            if first:
                logger.warning(
                    f"Sort elision: hint {indexes.name(spec)!r} on {kind!r} rejected ({exc}); explicit sort")
                indexes.invalidate(kind)
            return _find_sorted(collection, flt, sort, limit, session)
        # The hinted order is observed, not promised — verify it and fall back once if it does not hold.
        if order.is_sorted(docs, sort):
            return docs
        with _elision_lock:
            first = (kind, indexes.name(spec)) not in _elision_disabled
            _elision_disabled.add((kind, indexes.name(spec)))
        if first:
            logger.warning(f"Sort elision: index {indexes.name(spec)!r} on {kind!r} did not return a sorted "
                           f"order — explicit sort")
        return _find_sorted(collection, flt, sort, limit, session)

    # distinct: the first whole document per distinct value combination, in sort order. Mongo's own
    # collection.distinct() returns values of a single field only, so this takes an aggregation, sorted again
    # afterwards because the output of a $group no longer carries the original order.
    pipeline = [
        {"$match": flt},
        {"$sort": dict(sort)},
        {"$group": {"_id": {f: f"${f}" for f in distinct}, "__first__": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$__first__"}},
        {"$sort": dict(sort)},
    ]
    if limit:
        pipeline.append({"$limit": limit})
    return list(collection.aggregate(pipeline, session=session))


def _find_sorted(collection: Collection, flt: dict, sort: list[tuple[str, int]], limit: int,
                 session: ClientSession | None) -> list[dict]:
    """The plain path with an explicit ``sort()`` — the fallback of every sort elision."""
    cursor = collection.find(flt, session=session).sort(sort)
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


__all__ = ["delete", "get", "put", "run_in_transaction", "count"]
