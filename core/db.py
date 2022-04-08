# -*- coding: utf-8 -*-
import importlib, logging
from viur.core import conf

if conf["viur.db.engine"] =="viur.datastore":
	from viur.datastore import *
else:
	globals().update(importlib.import_module(conf["viur.db.engine"]).__dict__)

KeyClass = Key

__all__ = [KEY_SPECIAL_PROPERTY, DATASTORE_BASE_TYPES, SortOrder, Entity, Key, KeyClass, Put, Get, Delete, AllocateIDs,
		   Collision, keyHelper, fixUnindexableProperties, GetOrInsert, Query, QueryDefinition, IsInTransaction,
		   acquireTransactionSuccessMarker, RunInTransaction, config, startDataAccessLog, endDataAccessLog]
