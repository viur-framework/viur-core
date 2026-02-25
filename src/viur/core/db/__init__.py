import logging
import warnings

from . import cache
from .config import conf as config
from .query import Query
# new exports for 3.8
from .transport import (
    allocate_ids,
    AllocateIDs,
    count,
    Count,
    delete,
    Delete,
    get,
    Get,
    put,
    Put,
    run_in_transaction,
    RunInTransaction,
)
from .types import (
    current_db_access_log,
    DATASTORE_BASE_TYPES,
    Entity,
    KEY_SPECIAL_PROPERTY,
    Key,
    KeyType,
    QueryDefinition,
    SortOrder,
)
from .utils import (
    acquire_transaction_success_marker,
    encodeKey,
    end_data_access_log,
    endDataAccessLog,
    fix_unindexable_properties,
    get_or_insert,
    GetOrInsert,
    is_in_transaction,
    IsInTransaction,
    key_helper,
    keyHelper,
    normalize_key,
    normalizeKey,
    start_data_access_log,
    startDataAccessLog,
)

__all__ = [
    "KEY_SPECIAL_PROPERTY",
    "DATASTORE_BASE_TYPES",
    "SortOrder",
    "Entity",
    "QueryDefinition",
    "Key",
    "KeyType",
    "Query",
    "fix_unindexable_properties",
    "normalizeKey",
    "keyHelper",
    "Get",
    "Count",
    "Put",
    "Delete",
    "RunInTransaction",
    "IsInTransaction",
    "current_db_access_log",
    "GetOrInsert",
    "encodeKey",
    "acquire_transaction_success_marker",
    "AllocateIDs",
    "config",
    "startDataAccessLog",
    "endDataAccessLog",
    "cache",
    # new exports
    "allocate_ids",
    "get",
    "put",
    "is_in_transaction",
    "run_in_transaction",
    "count",
    "get_or_insert",
    "normalize_key",
    "key_helper",
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

    return super(__import__(__name__).__class__).__getattribute__(attr)
