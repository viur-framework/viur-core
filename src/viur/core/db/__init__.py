import typing as t

from . import cache, indexes, objectid, order
from .query import Query
from .transport import (
    count,
    delete,
    Document,
    get,
    put,
    run_in_transaction,
)
from .types import (
    current_db_access_log,
    KEY_SPECIAL_PROPERTY,
    QueryDefinition,
    QueryOrder,
    SortOrder,
    VALUE_TYPES,
)
from .utils import (
    acquire_transaction_success_marker,
    end_data_access_log,
    get_or_insert,
    is_in_transaction,
    start_data_access_log,
)

__all__ = [
    "KEY_SPECIAL_PROPERTY",
    "VALUE_TYPES",
    "SortOrder",
    "QueryOrder",
    "QueryDefinition",
    "Query",
    "current_db_access_log",
    "acquire_transaction_success_marker",
    "cache",
    # new exports
    "get",
    "put",
    "delete",
    "indexes",
    "objectid",
    "order",
    "Document",
    "is_in_transaction",
    "run_in_transaction",
    "count",
    "get_or_insert",
    "start_data_access_log",
    "end_data_access_log",
    "current_db_access_log",
]


def __getattr__(attr):
    if hint := _REMOVED_NAMES.get(attr):
        raise AttributeError(f"module 'viur.core.db' has no attribute {attr!r}: {hint}")
    raise AttributeError(f"module 'viur.core.db' has no attribute {attr!r}")


_REMOVED_NAMES: t.Final[dict[str, str]] = {
    # Datastore names without a counterpart on MongoDB
    "Key": "a key is now the _id string itself: db.Key(kind, name) -> name; "
           "the kind belongs at the call site (db.get(kind, _id), skel.read(_id))",
    "Entity": "a record is now a dict carrying '_id'; db.Entity(key) -> {'_id': _id}",
    "KeyType": "keys are str",
    "allocate_ids": "db.put creates a missing _id itself; to get an id up front: db.objectid.new_id()",
    "AllocateIDs": "db.put creates a missing _id itself; to get an id up front: db.objectid.new_id()",
    "key_helper": "an _id string no longer carries a kind; check isinstance(key, str) and key",
    "keyHelper": "an _id string no longer carries a kind; check isinstance(key, str) and key",
    "normalize_key": "keys are strings, there is nothing to normalize",
    "normalizeKey": "keys are strings, there is nothing to normalize",
    "GetOrInsert": "db.get_or_insert(kind, _id, **defaults)",
    "fix_unindexable_properties": "gone - MongoDB has no exclude-from-index list",
    "DATASTORE_BASE_TYPES": "is now called db.VALUE_TYPES",
    "Get": "db.get(kind, _id)", "Put": "db.put(kind, doc)", "Delete": "db.delete(kind, _id)",
    "Count": "db.count(kind, filter)", "RunInTransaction": "db.run_in_transaction(func, ...)",
    # Aliases removed in 4.0
    "config": "conf.db.memcache_client and conf.debug.trace_queries",
    "IsInTransaction": "db.is_in_transaction()",
    "encodeKey": "a key is already a string; use it as it is",
    "runSingleFilter": "db.transport.run_single_filter(query, limit, keys_only)",
    "startDataAccessLog": "db.start_data_access_log()",
    "endDataAccessLog": "db.end_data_access_log(outer_access_log)",
    "currentDbAccessLog": "db.current_db_access_log",
}
