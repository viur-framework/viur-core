# -*- coding: utf-8 -*-
from __future__ import annotations
import warnings
from viur.datastore import *

warnings.warn("The viur.core.db module is deprecated. Use viur.datastore instead", DeprecationWarning)

KeyClass = Key

Conflict = Error = AllocateIds = None

__all__ = [KEY_SPECIAL_PROPERTY, DATASTORE_BASE_TYPES, SortOrder, Entity, Key, KeyClass, Put, Get, Delete, AllocateIds,
		   Conflict, Error, keyHelper, fixUnindexableProperties, GetOrInsert, Query, IsInTransaction,
		   acquireTransactionSuccessMarker, RunInTransaction]
