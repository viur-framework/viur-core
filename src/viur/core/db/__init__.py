import logging
import warnings

from . import cache, indexes, objectid, order
from .config import conf as config
from .query import Query
# new exports for 3.8
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
    encodeKey,
    end_data_access_log,
    endDataAccessLog,
    get_or_insert,
    is_in_transaction,
    IsInTransaction,
    start_data_access_log,
    startDataAccessLog,
)

__all__ = [
    "KEY_SPECIAL_PROPERTY",
    "VALUE_TYPES",
    "SortOrder",
    "QueryOrder",
    "QueryDefinition",
    "Query",
    "IsInTransaction",
    "current_db_access_log",
    "encodeKey",
    "acquire_transaction_success_marker",
    "config",
    "startDataAccessLog",
    "endDataAccessLog",
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
    __DEPRECATED_NAMES = {
        # stuff prior viur-core < 3.8
        "currentDbAccessLog": ("current_db_access_log", current_db_access_log),
    }

    if replace := __DEPRECATED_NAMES.get(attr):
        msg = f"Use of `utils.{attr}` is deprecated; Use `{replace[0]}` instead!"
        warnings.warn(msg, DeprecationWarning, stacklevel=3)
        logging.warning(msg, stacklevel=3)

        ret = replace[1]

        # When this is a string, try to resolve by dynamic import
        if isinstance(ret, str):
            mod, item, attr = ret.rsplit(".", 2)
            mod = __import__(mod, fromlist=(item,))
            item = getattr(mod, item)
            ret = getattr(item, attr)

        return ret

    if hint := _REMOVED_NAMES.get(attr):
        raise AttributeError(f"module 'viur.core.db' has no attribute {attr!r}: {hint}")
    raise AttributeError(f"module 'viur.core.db' has no attribute {attr!r}")


_REMOVED_NAMES = {
    # Removed when the driver changed from the Datastore to MongoDB (CHANGELOG: "Breaking: MongoDB
    # instead of Datastore"). A clear hint here saves every migrating project the search — the old
    # fallback raised a misleading "'super' object has no attribute ...".
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
}
