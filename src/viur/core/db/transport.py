"""
MongoDB transport layer: the process-wide client, the session context and the document-based CRUD functions.

A kind is a collection of the same name and a key is the ``_id`` of a document — any non-empty ``str``.
:func:`put` generates an ObjectId hex when the caller supplies none, but viur also writes deterministic business
keys (the ``viur-conf`` singleton, the locks of unique constraints, ratelimit counters); there the uniqueness of
``_id`` carries the atomicity, which a separate field plus a query could not.

:func:`get` serves whatever the memcache already holds and asks MongoDB only for the remaining ids, in a single
``$in`` batch, warming the cache with the answer. Inside a transaction ``cache.get`` returns nothing, so reads
are always fresh there. :func:`put` warms the cache only after the write succeeded — a value that was never
persisted must never be cached — while :func:`delete` drops the cache entry before deleting, because a stale
entry that survived a failed delete would be served until it expires.

Writing several documents splits them by existence instead of upserting all of them: measured against Firestore
Enterprise with 100 documents, ``ReplaceOne(upsert=True)`` on new documents takes 1014 ms, plain inserts 49 ms
and ``ReplaceOne`` on existing documents 287 ms. The upsert that *creates* is the expensive path, so one lookup
for the existing ``_id``s (~30 ms) pays for itself; see :func:`_put_many`.

:func:`run_in_transaction` retries three times with an exponential backoff, and only for the conflicts
:func:`_is_transient` accepts; every other error propagates. Whether a read inside the transaction sees a value
written earlier in the same transaction is not guaranteed — keep such a value in a local variable instead of
reading it back.

Without an explicit order and with exactly one inequality filter, ``query._implicit_orders`` sorts ascending by
that field, the way the Datastore did silently; only that makes an index ``(equality fields…, field, _id)``
usable for the sort elision below. Cursors are keyset pagination: ``QueryDefinition.startCursor``/``endCursor``
carry the sort values of a row already seen, which ``query._after_condition``/``_before_condition`` turn into a
lower or upper bound that is ``$and``-ed onto the filter. ``query._to_mongo_sort`` always appends ``_id`` as the
last sort criterion, so that bound is unambiguous. An ``Inverted*`` query reads the same cursor with an
inclusive instead of an exclusive bound and flips the result into display order afterwards.

Firestore Enterprise fetches every index hit before applying the limit when an explicit sort is present; without
a sort the scan stops after ``limit`` documents. :func:`_find` therefore drops ``sort()`` whenever an existing
index already yields the requested order (``indexes.eligible``), hints that index instead and verifies the order
client-side (``order.is_sorted``). An unsorted result or a rejected hint falls back to the explicit sort and
turns the elision off for that ``(kind, index)`` pair for the rest of the process, warning once while doing so,
so a broken order or a vanished index does not make every further query try the hint path again. The elision
never changes the result, only the way to it.
"""
from __future__ import annotations

import contextvars
import datetime
import logging
import threading
import time
import typing as t

import pymongo
from deprecated.sphinx import deprecated
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
"""pymongo itself waits 30 s for server selection and 20 s per connection attempt. Without an explicit bound
every request against an unreachable database blocks that long, again for the next request — with
``gunicorn --threads 2`` that is enough to block the whole instance instead of failing fast. A development
machine whose DNS answers with an unroutable IPv6 address waits the full connect timeout before trying IPv4
(measured 21 s for the first access, per new pool connection). 5 s is generous for a short network hiccup and
far below the request timeouts of App Engine/Cloud Run."""

_mongo_client: MongoClient | None = None
_mongo_lock = threading.Lock()
"""Guards the one-time construction of ``_mongo_client``. A ``MongoClient`` is built to be shared across
threads afterwards; only its creation needs the lock, otherwise two concurrent first accesses build two
connection pools."""

_current_session: contextvars.ContextVar[ClientSession | None] = contextvars.ContextVar(
    "viur_db_session", default=None
)
"""The running transaction, separate per thread and per async task.

A ``MongoClient`` is built to be shared, a ``ClientSession`` explicitly is not, so the session cannot be kept on
the client the way the Datastore client kept its transaction in a thread-local stack — it is kept here."""

_elision_disabled: set[tuple[str, str]] = set()
_elision_lock = threading.Lock()
"""Guards ``_elision_disabled``, a set of ``(kind, index name)`` pairs whose sort elision is off for the rest
of the process; held only around the set operation, never around I/O — see the module docstring."""

Document: t.TypeAlias = dict[str, t.Any]
"""A record as the driver returns it: a dict carrying an ``_id``."""


def _mongo() -> MongoClient:
    """The shared client, built on first access.

    Lazily instead of at import time: a ``datastore.Client()`` built at import used to force every test to
    provide credentials before the first ``import viur.core``.
    """
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
                    # BSON stores dates as UTC milliseconds and pymongo returns them NAIVE by default. The
                    # Datastore returned aware UTC and the whole core compares against utils.utcNow() (aware),
                    # where a naive date from the database raises TypeError. Parity: aware UTC.
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


def _collection(kind: str) -> Collection:
    """The collection belonging to a kind — one to one, under the same name."""
    return _mongo()[conf.db.name][kind]


def _check_id(_id: t.Any) -> None:
    """Reject anything but a non-empty ``str`` — on deterministic keys see the module docstring."""
    if not isinstance(_id, str) or not _id:
        raise ValueError(f"_id must be a non-empty str, got {_id!r}")


def get(kind: str, ids: str | list[str] | set[str] | tuple[str, ...]) -> Document | list[Document] | None:
    """Load one document (or several) from *kind*.

    A single id yields the document or ``None``, a collection of ids yields the documents found in request
    order, leaving missing ones out. Several ids are recognized by the collection type, not by iterability — a
    ``str`` is iterable itself. On caching and batching see the module docstring.

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
        fetched = list(_collection(kind).find({"_id": {"$in": missing}}, session=_current_session.get()))
        if fetched:
            cache.put(kind, fetched)
        for doc in fetched:
            found[doc["_id"]] = doc

    if not is_multiple:
        return found.get(id_list[0])
    return [found[_id] for _id in id_list if _id in found]


def put(kind: str, docs: Document | list[Document]) -> Document | list[Document]:
    """Write one document (or several) to *kind*.

    A missing ``_id`` is generated and written into the given dict, so the caller knows the id of the record
    just written. On the cost of writing several documents and on caching see the module docstring.

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

    col = _collection(kind)
    session = _current_session.get()
    if len(doc_list) == 1:
        # For a single document the lookup of _put_many does not pay off.
        col.replace_one({"_id": doc_list[0]["_id"]}, doc_list[0], upsert=True, session=session)
    else:
        _put_many(col, doc_list, session)

    cache.put(kind, docs)
    return docs


def _put_many(col: Collection, doc_list: list[Document], session: ClientSession | None) -> None:
    """Insert what is new and replace what exists, instead of upserting everything (costs: module docstring).

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


def delete(kind: str, ids: str | list[str] | set[str] | tuple[str, ...]) -> None:
    """Delete documents from *kind*; unknown ids are not an error.

    The cache is dropped before the deletion itself, see the module docstring.
    """
    id_list = list(ids) if isinstance(ids, (list, set, tuple)) else [ids]
    if not id_list:
        return
    cache.delete(kind, id_list)
    _collection(kind).delete_many({"_id": {"$in": id_list}}, session=_current_session.get())


def count(kind: str, flt: dict | None = None, up_to: int | None = None) -> int:
    """Count the documents in *kind*, optionally narrowed by a Mongo filter and cut short by *up_to*."""
    # ``limit`` makes MongoDB stop counting once *up_to* hits are found, instead of counting through the whole
    # (possibly much larger) result set — the cost bound ``Query.count(up_to=...)`` has always promised.
    kwargs = {"limit": up_to} if up_to else {}
    return _collection(kind).count_documents(flt or {}, session=_current_session.get(), **kwargs)


def run_in_transaction(func: t.Callable, *args, **kwargs) -> t.Any:
    """Run *func* in a transaction — either all of its writes are applied or none of them.

    If a transaction is already running, *func* runs inside it without a second one being opened. On the retry
    and read-your-own-writes semantics see the module docstring.

    :param func: The callable to run; further arguments are passed on to it.
    :return: Whatever *func* returned.
    :raises RuntimeError: When the retries are exhausted.
    """
    if _current_session.get() is not None:
        return func(*args, **kwargs)

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
            if not _is_transient(exc):
                raise
            logger.error(f"Transaction failed with a conflict, trying again in {2 ** i} seconds")
            time.sleep(2 ** i)
            continue
    else:
        raise RuntimeError("Maximum transaction retries exceeded")

    return res


def _is_transient(exc: pymongo.errors.PyMongoError) -> bool:
    """A retryable transaction conflict? MongoDB sets the label, Firestore reports code 112 ("Aborted")."""
    if exc.has_error_label("TransientTransactionError"):
        return True
    return isinstance(exc, pymongo.errors.OperationFailure) and exc.code == 112


def run_single_filter(query: QueryDefinition, limit: int, keys_only: bool) -> list[dict | str]:
    """Run a single ``QueryDefinition`` against MongoDB and return the hits.

    *query* is the ``QueryDefinition`` itself, not the ``Query`` — that is how ``Query._run_single_filter_query``
    calls, and for a multi-query (``SpatialBone``, ``RandomSliceBone``) exactly one of the definitions in
    ``Query.queries`` arrives here at a time. On implicit ordering and cursors see the module docstring.

    :param query: The single query definition to run.
    :param limit: The maximum number of documents to return.
    :param keys_only: Return only the ``_id`` of each hit instead of the whole document.
    :return: The documents found, or their ``_id``s when *keys_only* is set.
    """
    from .query import (
        _after_condition, _before_condition, _dotted_get, _implicit_orders, _to_mongo_filter, _to_mongo_sort,
    )

    flt = _to_mongo_filter(query.filters, query.or_filters)
    eq_fields = _equality_fields(flt)
    orders = query.orders or _implicit_orders(query.filters or {})
    # A limit-1 lookup without any order (neither explicit nor implicit), without a cursor and without distinct
    # sends no sort(): the scan stops at the first hit instead of loading and sorting every hit.
    lookup = limit == 1 and not orders and not query.startCursor and not query.endCursor and not query.distinct
    sort = [] if lookup else _to_mongo_sort(orders)
    inverted = any(
        order in (SortOrder.InvertedAscending, SortOrder.InvertedDescending)
        for _, order in (query.orders or [])
    )

    # Keyset continuation: an Inverted* query reads its start cursor inclusively, a plain one exclusively.
    extra = []
    if query.startCursor:
        extra.append(_after_condition(sort, query.startCursor, inclusive=inverted))
    if query.endCursor:
        extra.append(_before_condition(sort, query.endCursor))
    if extra:
        flt = {"$and": [flt, *extra]} if flt else ({"$and": extra} if len(extra) > 1 else extra[0])

    docs = _find(query.kind, flt, sort, query.distinct, limit, eq_fields=eq_fields)

    # The cursor of this run, and the flip back into display order.
    query.currentCursor = {field: _dotted_get(docs[-1], field) for field, _ in sort} if docs and sort else None
    if inverted:
        docs.reverse()

    if keys_only:
        return [d["_id"] for d in docs]
    return docs


def _equality_fields(flt: dict) -> frozenset[str]:
    """The top-level fields of *flt* holding a plain equality value — the index prefix for ``indexes.eligible``."""
    # Neither an operator dict nor ``$and``/``$or`` counts; everything else is filtered residually.
    return frozenset(
        field for field, value in flt.items()
        if not field.startswith("$") and not (isinstance(value, dict) and any(k.startswith("$") for k in value))
    )


def _find(kind: str, flt: dict, sort: list[tuple[str, int]], distinct: list[str] | None, limit: int,
          *, eq_fields: frozenset[str] = frozenset()) -> list[dict]:
    """The read behind :func:`run_single_filter`: a plain ``find``, an elided sort, or an aggregation.

    *distinct* takes a completely different route through the driver (an aggregation instead of ``find``),
    while cursor, inversion and ``keys_only`` are the same for both — hence the split from
    :func:`run_single_filter`. On the sort elision see the module docstring.

    :param kind: The kind to read from.
    :param flt: The Mongo filter.
    :param sort: The Mongo sort; empty for a lookup without any order.
    :param distinct: The fields to return one document per value combination of.
    :param limit: The maximum number of documents; ``0`` for no limit.
    :param eq_fields: The equality fields of *flt*, the prefix an index has to carry.
    :return: The documents found, in the order asked for.
    """
    from . import indexes, order

    collection = _collection(kind)
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


@deprecated(version="3.8.0", reason="Use 'run_single_filter' instead")
def runSingleFilter(query: QueryDefinition, limit: int) -> list[dict]:
    run_single_filter(query, limit)


__all__ = ["delete", "get", "put", "run_in_transaction", "count"]
