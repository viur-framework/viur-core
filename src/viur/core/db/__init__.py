from . import cache
from .config import conf as config
from .errors import *
from .query import Query
from .transport import AllocateIDs, Delete, Get, Put, RunInTransaction, Count
from .types import (
    currentDbAccessLog,
    DATASTORE_BASE_TYPES,
    Entity,
    KEY_SPECIAL_PROPERTY,
    Key,
    QueryDefinition,
    SkelListRef,
    SortOrder,
)
from .utils import (
    acquireTransactionSuccessMarker,
    encodeKey,
    endDataAccessLog,
    fixUnindexableProperties,
    GetOrInsert,
    IsInTransaction,
    keyHelper,
    normalizeKey,
    startDataAccessLog,
)

import logging

# silencing requests' debugging
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

__all__ = [
    "KEY_SPECIAL_PROPERTY",
    "DATASTORE_BASE_TYPES",
    "SortOrder",
    "SkelListRef",
    "Entity",
    "QueryDefinition",
    "Key",
    "Query",
    "fixUnindexableProperties",
    "normalizeKey",
    "keyHelper",
    "Get",
    "Count",
    "Put",
    "Delete",
    "RunInTransaction",
    "IsInTransaction",
    "currentDbAccessLog",
    "GetOrInsert",
    "encodeKey",
    "acquireTransactionSuccessMarker",
    "AllocateIDs",
    "config",
    "startDataAccessLog",
    "endDataAccessLog",
    "ViurDatastoreError",
    "AbortedError",
    "CollisionError",
    "DeadlineExceededError",
    "FailedPreconditionError",
    "InternalError",
    "InvalidArgumentError",
    "NotFoundError",
    "PermissionDeniedError",
    "ResourceExhaustedError",
    "UnauthenticatedError",
    "UnavailableError",
    "NoMutationResultsError",
    "cache",
]
