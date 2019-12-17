# -*- coding: utf-8 -*-
# from google.appengine.api import datastore, datastore_types, datastore_errors
# from google.appengine.datastore import datastore_query, datastore_rpc
# from google.appengine.api import memcache
# from google.appengine.api import search
from viur.core.config import conf
from viur.core import utils
import logging, threading
from google.cloud import firestore
from google.cloud.firestore_v1beta1 import _helpers
from google.cloud.firestore_v1beta1 import field_path as field_path_module
from google.cloud.firestore_v1beta1.proto import common_pb2
from google.cloud.firestore_v1beta1.watch import Watch
from google.api_core import exceptions
from google.cloud import firestore
from datetime import datetime, timedelta
from typing import Union, Tuple, List, Dict, Iterable, Any
from time import time, mktime
import google.auth
from functools import partial
from viur.core import request
from google.protobuf import wrappers_pb2, struct_pb2, timestamp_pb2
from collections import namedtuple
from google.type import latlng_pb2
from copy import deepcopy
from google.cloud import datastore


"""
	Tiny wrapper around *google.appengine.api.datastore*.

	This just ensures that operations issued directly through the database-api
	doesn't interfere with ViURs internal caching. If you need skeletons anyway,
	query the database using skel.all(); its faster and is able to serve more
	requests from cache.
"""

__cacheLockTime__ = 42  # Prevent an entity from creeping into the cache for 42 Secs if it just has been altered.
__cacheTime__ = 15 * 60  # 15 Mins
__CacheKeyPrefix__ = "viur-db-cache:"  # Our Memcache-Namespace. Dont use that for other purposes
__MemCacheBatchSize__ = 30
__undefinedC__ = object()
__currentTransaction__ = threading.local()

# Firestore specific stuff
__OauthScopesFirestore__ = (
	"https://www.googleapis.com/auth/cloud-platform",
	"https://www.googleapis.com/auth/datastore",
)
__database__ = "projects/%s/databases/(default)" % utils.projectID
__documentRoot__ = "projects/%s/databases/(default)/documents/" % utils.projectID
__documentRootLen__ = len(__documentRoot__)  # A slice should be faster than fullKey.replace(__documentRoot__, "")
#__channel__ = grpc_helpers.create_channel("firestore.googleapis.com:443", scopes=__OauthScopesFirestore__)
#__firestoreStub__ = firestore_pb2_grpc.FirestoreStub(channel=__channel__)
__client__ = datastore.Client()

## Custom Datatypes
GeoPoint = namedtuple("GeoPoint", ["latitude", "longitude"])  # Fixme: Currently not used
Key = namedtuple("Key", ["collection", "name"])

#_operatorMap = {
#	"<": enums.StructuredQuery.FieldFilter.Operator.LESS_THAN,
#	"<=": enums.StructuredQuery.FieldFilter.Operator.LESS_THAN_OR_EQUAL,
#	"=": enums.StructuredQuery.FieldFilter.Operator.EQUAL,
#	">=": enums.StructuredQuery.FieldFilter.Operator.GREATER_THAN_OR_EQUAL,
#	">": enums.StructuredQuery.FieldFilter.Operator.GREATER_THAN,
#	"AC": enums.StructuredQuery.FieldFilter.Operator.ARRAY_CONTAINS,
#}

Entity = datastore.Entity
KeyClass = datastore.Key


## Helper functions for dealing with protobuffs etc.

_generateNewId = partial(utils.generateRandomString, length=20)



def PutAsync(entities, **kwargs):
	"""
		Asynchronously store one or more entities in the data store.

		This function is identical to :func:`server.db.Put`, except that it
		returns an asynchronous object. Call ``get_result()`` on the return value to
		block on the call and get the results.
	"""
	raise NotImplementedError()
	if isinstance(entities, Entity):
		entities._fixUnindexedProperties()
	elif isinstance(entities, list):
		for entity in entities:
			assert isinstance(entity, Entity)
			entity._fixUnindexedProperties()
	if conf["viur.db.caching"] > 0:
		if isinstance(entities, Entity):  # Just one:
			if entities.is_saved():  # Its an update
				memcache.delete(str(entities.key()), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__)
		elif isinstance(entities, list):
			for entity in entities:
				assert isinstance(entity, Entity)
				if entity.is_saved():  # Its an update
					memcache.delete(str(entity.key()), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__)
	return (datastore.PutAsync(entities, **kwargs))


def Put(entries):
	def fixUnindexed(entry):
		def hasUnindexed(prop):
			if isinstance(prop, dict):
				return any([hasUnindexed(x) for x in prop.values()])
			elif isinstance(prop, list):
				return any([hasUnindexed(x) for x in prop])
			elif isinstance(prop, str):
				return len(prop) >= 500
			else:
				return False

		resList = []
		for k, v in entry.items():
			if hasUnindexed(v):
				if isinstance(v, dict):
					innerEntry = Entity()
					innerEntry.update(v)
					entry[k] = fixUnindexed(innerEntry)
				else:
					resList.append(k)
		entry.exclude_from_indexes = resList
		return entry
	if isinstance(entries, list):
		return [Put(x) for x in entries]
	entry = fixUnindexed(entries)
	return __client__.put(entry)

#Put = __client__.put


def Put__(entities: Union[Entity, List[Entity]], **kwargs) -> None:
	"""
		Store one or more entities in the data store.

		The entities may be new or previously existing. For new entities,
		``Put()`` will fill in the app id and key assigned by the data store.

		:param entities: Entity or list of entities to be stored.
		:type entities: :class:`server.db.Entity` | list of :class:`server.db.Entity`

		:param config: Optional configuration to use for this request. This must be specified\
		as a keyword argument.
		:type config: dict

		:returns: If the argument ``entities`` is a single :class:`server.db.Entity`, \
		a single Key is returned. If the argument is a list of :class:`server.db.Entity`, \
		a list of Keys will be returned.
		:rtype: Key | list of keys

		:raises: :exc:`TransactionFailedError`, if the action could not be committed.
	"""
	try:
		currentTransaction = __currentTransaction__.transactionData
	except AttributeError:
		currentTransaction = None
	if isinstance(entities, list):  # FIXME: Use a WriteBatch instead
		for x in entities:
			Put(x)
	if not entities.name:
		# This will be an add
		entities.name = _generateNewId()
	documentPb = document_pb2.Document(name="%s%s/%s" % (__documentRoot__, entities.collection, entities.name),
									   fields={key: _pythonValToProtoValue(value) for key, value in entities.items()})
	if currentTransaction:
		# We have to enqueue the writes to the transaction
		if not entities.collection in currentTransaction["pendingChanges"]:
			currentTransaction["pendingChanges"][entities.collection] = {}
		currentTransaction["pendingChanges"][entities.collection][entities.name] = entities
		currentTransaction["lastQueries"] = []  # We have a change where, void all previous queries
		return
	else:
		# No transaction, write directly into firestore
		updateDocumentRequest = firestore_pb2.UpdateDocumentRequest(
			document=documentPb,
			update_mask=common_pb2.DocumentMask(field_paths=entities.keys()),
		)
		res = __firestoreStub__.UpdateDocument(updateDocumentRequest)
		return  # FIXME: Return-Value? Keys/List of Keys?
	assert False, "Should never reach this"
	if isinstance(entities, Entity):
		entities._fixUnindexedProperties()
	elif isinstance(entities, list):
		for entity in entities:
			assert isinstance(entity, Entity)
			entity._fixUnindexedProperties()
	if conf["viur.db.caching"] > 0:
		if isinstance(entities, Entity):  # Just one:
			if entities.is_saved():  # Its an update
				memcache.delete(str(entities.key()), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__)
		elif isinstance(entities, list):
			for entity in entities:
				assert isinstance(entity, Entity)
				if entity.is_saved():  # Its an update
					memcache.delete(str(entity.key()), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__)
	return (datastore.Put(entities, **kwargs))


def GetAsync(keys, **kwargs):
	"""
		Asynchronously retrieves one or more entities from the data store.

		This function is identical to :func:`server.db.Get`, except that it
		returns an asynchronous object. Call ``get_result()`` on the return value to
		block on the call and get the results.
	"""
	raise NotImplementedError()

	class AsyncResultWrapper:
		"""
			Wraps an result thats allready there into something looking
			like an RPC-Object.
		"""

		def __init__(self, res):
			self.res = res

		def get_result(self):
			return (self.res)

	if conf["viur.db.caching"] > 0 and not datastore.IsInTransaction():
		if isinstance(keys, datastore_types.Key) or isinstance(keys, str):  # Just one:
			res = memcache.get(str(keys), namespace=__CacheKeyPrefix__)
			if res:
				return (AsyncResultWrapper(res))
	# Either the result wasnt found, or we got a list of keys to fetch;
	# --> no caching possible
	return (datastore.GetAsync(keys, **kwargs))


Get = __client__.get


def Get__(keys: Union[Key, List[Key]], **kwargs) -> Union[None, Entity, List[Entity]]:
	"""
		Retrieve one or more entities from the data store.

		Retrieves the entity or entities with the given key(s) from the data store
		and returns them as fully populated :class:`server.db.Entity` objects.

		If there is an error, the function raises a subclass of :exc:`datastore_errors.Error`.

		If keys is a single key or str, an Entity will be returned,
		or :exc:`EntityNotFoundError` will be raised if no existing entity matches the key.

		However, if keys is a list or tuple, a list of entities will be returned
		that corresponds to the sequence of keys. It will include entities for keys
		that were found and None placeholders for keys that were not found.

		:param keys: Key, str or list of keys or strings to be retrieved.
		:type keys: Key | str | list of Key | list of str

		:param config: Optional configuration to use for this request. This must be specified\
		as a keyword argument.
		:type config: dict

		:returns: Entity or list of Entity objects corresponding to the specified key(s).
		:rtype: :class:`server.db.Entity` | list of :class:`server.db.Entity`
	"""
	mergeWithUpdatedEntry = lambda entry, collection, key: entry
	try:
		currentTransaction = __currentTransaction__.transactionData
		if currentTransaction:
			def mergeWithUpdatedEntry(entry, collection, key):
				if not collection in currentTransaction["pendingChanges"] or not \
						key in currentTransaction["pendingChanges"][collection]:
					return entry
				return currentTransaction["pendingChanges"][collection][key]
	except AttributeError:
		currentTransaction = None
	if isinstance(keys, list):  # In this case issue a BatchGetDocumentsRequest to avoid multiple roundtrips
		if any(["/" in collection or "/" in name for collection, name in keys]):
			raise ValueError("Collections or Names must not contain a /")
		batchGetDocumentsRequest = firestore_pb2.BatchGetDocumentsRequest(
			database=__database__,
			documents=["%s%s/%s" % (__documentRoot__, collection, name) for collection, name in keys],
			transaction=currentTransaction["transactionKey"] if currentTransaction else None)
		resultPromise = __firestoreStub__.BatchGetDocuments(batchGetDocumentsRequest)
		# Documents returned are not guaranteed to be in the same order as requested, so we have to fix this first
		tmpDict = {}
		for item in resultPromise:
			if item.found.name:  # We also get empty results for keys not found
				tmpDict[item.found.name] = _protoMapToEntry(
					protBufFields=item.found.fields,
					keyPath=item.found.name[__documentRootLen__:].split("/"))
		return [mergeWithUpdatedEntry(tmpDict.get("%s%s/%s" % (__documentRoot__, *key)), *key) for key in keys]
	else:  # We fetch a single Document and can use the simpler GetDocumentRequest
		collection, name = keys
		if "/" in collection or "/" in name:
			raise ValueError("Collections or Names must not contain a /")
		getDocumentRequest = firestore_pb2.GetDocumentRequest(
			name="%s%s/%s" % (__documentRoot__, collection, name),
			transaction=currentTransaction["transactionKey"] if currentTransaction else None)
		try:
			resultPB = __firestoreStub__.GetDocument(getDocumentRequest)
		except GrpcRendezvousError as e:
			if e.code() == GrpcStatusCode.NOT_FOUND:
				# If a given key is not found, we simply return None instead of raising an exception
				return mergeWithUpdatedEntry(None, collection, name)
			raise
		return mergeWithUpdatedEntry(_protoMapToEntry(resultPB.fields, keys), collection, name)

	## OLD Datastore-Code
	if conf["viur.db.caching"] > 0 and not datastore.IsInTransaction():
		if isinstance(keys, datastore_types.Key) or isinstance(keys, basestring):  # Just one:
			res = memcache.get(str(keys), namespace=__CacheKeyPrefix__)
			if not res:  # Not cached - fetch and cache it :)
				res = Entity.FromDatastoreEntity(datastore.Get(keys, **kwargs))
				res["key"] = str(res.key())
				memcache.set(str(res.key()), res, time=__cacheTime__, namespace=__CacheKeyPrefix__)
			return (res)
		# Either the result wasnt found, or we got a list of keys to fetch;
		elif isinstance(keys, list):
			# Check Memcache first
			cacheRes = {}
			tmpRes = []
			keyList = [str(x) for x in keys]
			while keyList:  # Fetch in Batches of 30 entries, as the max size for bulk_get is limited to 32MB
				currentBatch = keyList[:__MemCacheBatchSize__]
				keyList = keyList[__MemCacheBatchSize__:]
				cacheRes.update(memcache.get_multi(currentBatch, namespace=__CacheKeyPrefix__))
			# Fetch the rest from DB
			missigKeys = [x for x in keys if not str(x) in cacheRes]
			dbRes = [Entity.FromDatastoreEntity(x) for x in datastore.Get(missigKeys) if x is not None]
			# Cache what we had fetched
			saveIdx = 0
			while len(dbRes) > saveIdx * __MemCacheBatchSize__:
				cacheMap = {str(obj.key()): obj for obj in
							dbRes[saveIdx * __MemCacheBatchSize__:(saveIdx + 1) * __MemCacheBatchSize__]}
				try:
					memcache.set_multi(cacheMap, time=__cacheTime__, namespace=__CacheKeyPrefix__)
				except:
					pass
				saveIdx += 1
			for key in [str(x) for x in keys]:
				if key in cacheRes:
					tmpRes.append(cacheRes[key])
				else:
					for e in dbRes:
						if str(e.key()) == key:
							tmpRes.append(e)
							break
			if conf["viur.debug.traceQueries"]:
				logging.debug("Fetched a result-set from Datastore: %s total, %s from cache, %s from datastore" % (
					len(tmpRes), len(cacheRes.keys()), len(dbRes)))
			return (tmpRes)
	if isinstance(keys, list):
		return ([Entity.FromDatastoreEntity(x) for x in datastore.Get(keys, **kwargs)])
	else:
		return (Entity.FromDatastoreEntity(datastore.Get(keys, **kwargs)))


def GetOrInsert(key: Key, **kwargs):
	"""
		Either creates a new entity with the given key, or returns the existing one.

		Its guaranteed that there is no race-condition here; it will never overwrite an
		previously created entity. Extra keyword arguments passed to this function will be
		used to populate the entity if it has to be created; otherwise they are ignored.

		:param key: The key which will be fetched or created. \
		If key is a string, it will be used as the name for the new entity, therefore the \
		collectionName is required in this case.
		:type key: server.db.Key | str
		:param kindName: The data kind to use for that entity. Ignored if key is a db.Key.
		:type kindName: str

		:param parent: The parent entity of the entity.
		:type parent: db.Key or None

		:returns: Returns the wanted Entity.
		:rtype: server.db.Entity
	"""

	def txn(key, kwargs):
		obj = Get(key)
		if not obj:
			obj = Entity(key)
			for k, v in kwargs.items():
				obj[k] = v
			Put(obj)
		return obj

	if IsInTransaction():
		return txn(key, kwargs)
	return RunInTransaction(txn, key, kwargs)

	def txn(key, kwargs):
		try:
			res = Entity.FromDatastoreEntity(datastore.Get(key))
		except datastore_errors.EntityNotFoundError:
			res = Entity(kind=key.kind(), parent=key.parent(), name=key.name(), id=key.id())
			for k, v in kwargs.items():
				res[k] = v
			datastore.Put(res)
		return (res)

	if not isinstance(key, datastore_types.Key):
		try:
			key = datastore_types.Key(encoded=key)
		except:
			assert kindName
			key = datastore_types.Key.from_path(kindName, key, parent=parent)
	if datastore.IsInTransaction():
		return txn(key, kwargs)

	return datastore.RunInTransaction(txn, key, kwargs)


def DeleteAsync(keys, **kwargs):
	"""
		Asynchronously deletes one or more entities from the data store.

		This function is identical to :func:`server.db.Delete`, except that it
		returns an asynchronous object. Call ``get_result()`` on the return value to
		block on the call and get the results.
	"""
	raise NotImplementedError()
	if conf["viur.db.caching"] > 0:
		if isinstance(keys, datastore_types.Key):  # Just one:
			memcache.delete(str(keys), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__)
		elif isinstance(keys, list):
			for key in keys:
				assert isinstance(key, datastore_types.Key) or isinstance(key, basestring)
				memcache.delete(str(key), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__)
	return (datastore.DeleteAsync(keys, **kwargs))


Delete_ = __client__.delete

def Delete(*args, **kwargs):
	return

def Delete__(keys: Union[Key, List[Key]], **kwargs) -> None:
	"""
		Deletes one or more entities from the data store.

		:warning: Permanently deletes entities, use with care!

		Deletes the given entity or entities from the data store. You can only delete
		entities from your app. If there is an error, the function raises a
		subclass of :exc:`datastore_errors.Error`.

		:param keys: Key, str or list of keys or strings to be deleted.
		:type keys: Key | str | list of Key | list of str

		:param config: Optional configuration to use for this request. This must be specified\
		as a keyword argument.
		:type config: dict

		:raises: :exc:`TransactionFailedError`, if the deletion could not be committed.
	"""
	try:
		currentTransaction = __currentTransaction__.transactionData
	except AttributeError:
		currentTransaction = None
	if not isinstance(keys, list):
		keys = [keys]
	for collection, name in keys:
		if "/" in collection or "/" in name:
			raise ValueError("Collections or Names must not contain a /")
		if currentTransaction:
			# Just mark that entry as pending delete
			if not collection in currentTransaction["pendingChanges"]:
				currentTransaction["pendingChanges"][collection] = {}
			currentTransaction["pendingChanges"][collection][name] = None
			currentTransaction["lastQueries"] = []  # We have a change where, void all previous queries
		else:
			# No Txn - delete directly
			deleteDocumentRequest = firestore_pb2.DeleteDocumentRequest(
				name="%s%s/%s" % (__documentRoot__, collection, name))
			try:
				resultPB = __firestoreStub__.DeleteDocument(deleteDocumentRequest)
			except GrpcRendezvousError as e:
				if e.code() == GrpcStatusCode.NOT_FOUND:
					# If a given key is not found, we simply return None instead of raising an exception
					return None
				raise
	return
	if conf["viur.db.caching"] > 0:
		if isinstance(keys, datastore_types.Key) or isinstance(keys, basestring):  # Just one:
			memcache.delete(str(keys), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__)
		elif isinstance(keys, list):
			for key in keys:
				assert isinstance(key, datastore_types.Key) or isinstance(key, basestring)
				memcache.delete(str(key), namespace=__CacheKeyPrefix__, seconds=__cacheLockTime__)
	return (datastore.Delete(keys, **kwargs))



class Query(object):
	"""
		Base Class for querying the firestore
	"""

	# Fixme: Typing for Skeleton-Class we can't import here?
	def __init__(self, collection: str, srcSkelClass: Union[None, Any] = None, *args, **kwargs):
		super(Query, self).__init__()
		self.collection = collection
		self.srcSkel = srcSkelClass
		self.filters: Union[None, Dict[str: Any], List[Dict[str: Any]]] = {}
		self.orders: List[Tuple[str, int]] = [(KEY_SPECIAL_PROPERTY, ASCENDING)]
		self.amount: int = 30
		self._filterHook = None
		self._orderHook = None
		self._startCursor = None
		self._endCursor = None
		self._customMultiQueryMerge = None  # Sometimes, the default merge functionality from MultiQuery is not sufficient
		self._calculateInternalMultiQueryAmount = None  # Some (Multi-)Queries need a different amount of results per subQuery than actually returned
		self.customQueryInfo = {}  # Allow carrying custom data along with the query. Currently only used by spartialBone to record the guranteed correctnes
		self.origCollection = collection
		self._lastEntry = None
		self._fulltextQueryString = None
		self.lastCursor = None

	def setFilterHook(self, hook):
		"""
			Installs *hook* as a callback function for new filters.

			*hook* will be called each time a new filter constrain is added to the query.
			This allows e. g. the relationalBone to rewrite constrains added after the initial
			processing of the query has been done (e. g. by ``listFilter()`` methods).

			:param hook: The function to register as callback. \
			A value of None removes the currently active hook.
			:type hook: callable

			:returns: The previously registered hook (if any), or None.
		"""
		old = self._filterHook
		self._filterHook = hook
		return (old)

	def setOrderHook(self, hook):
		"""
			Installs *hook* as a callback function for new orderings.

			*hook* will be called each time a :func:`db.Query.order` is called on this query.

			:param hook: The function to register as callback. \
			A value of None removes the currently active hook.
			:type hook: callable

			:returns: The previously registered hook (if any), or None.
		"""
		old = self._orderHook
		self._orderHook = hook
		return (old)

	def mergeExternalFilter(self, filters):
		"""
			Safely merges filters according to the data model.

			Its only valid to call this function if the query has been created using
			:func:`server.skeleton.Skeleton.all`.

			Its safe to pass filters received from an external source (a user);
			unknown/invalid filters will be ignored, so the query-object is kept in a
			valid state even when processing malformed data.

			If complex queries are needed (e.g. filter by relations), this function
			shall also be used.

			See also :func:`server.db.Query.filter` for simple filters.

			:param filters: A dictionary of attributes and filter pairs.
			:type filters: dict

			:returns: Returns the query itself for chaining.
			:rtype: server.db.Query
		"""
		from viur.core.bones import baseBone, relationalBone
		if "id" in filters:
			self.datastoreQuery = None
			logging.error("Filtering by id is no longer supported. Use key instead.")
			return self
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		if self.filters is None:  # This query is allready unsatifiable and adding more constrains to this wont change this
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
				self.filters = None
		bones = [(y, x) for x, y in skel.items()]
		try:
			# First, filter non-relational bones
			for bone, key in [x for x in bones if not isinstance(x[0], relationalBone)]:
				bone.buildDBFilter(key, skel, self, filters)
			# Second, process orderings of non-relational bones
			for bone, key in [x for x in bones if not isinstance(x[0], relationalBone)]:
				bone.buildDBSort(key, skel, self, filters)
			# Now filter relational bones
			for bone, key in [x for x in bones if isinstance(x[0], relationalBone)]:
				bone.buildDBFilter(key, skel, self, filters)
			# finally process orderings of relational bones
			for bone, key in [x for x in bones if isinstance(x[0], relationalBone)]:
				bone.buildDBSort(key, skel, self, filters)
		except RuntimeError as e:
			logging.exception(e)
			self.filters = None
			return self
		if "cursor" in filters and filters["cursor"] and filters["cursor"].lower() != "none":
			self.setCursor(filters["cursor"])
		if "amount" in filters and str(filters["amount"]).isdigit() and int(filters["amount"]) > 0 and int(
				filters["amount"]) <= 100:
			self.limit(int(filters["amount"]))
		if "postProcessSearchFilter" in dir(skel):
			skel.postProcessSearchFilter(self, filters)
		return self

	def filter(self, filter, value=__undefinedC__):
		"""
			Adds a new constraint to this query.

			The following examples are equivalent: ``filter( "name", "John" )``
			and ``filter( {"name": "John"} )``.

			See also :func:`server.db.Query.mergeExternalFilter` for a safer filter implementation.

			:param filter: A dictionary to read the filters from, or a string (name of that filter)
			:type filter: dict | str

			:param value: The value of that filter. Only valid, if *key* is a string.
			:type: value: int | long | float | bytes | string | list | datetime

			:returns: Returns the query itself for chaining.
			:rtype: server.db.Query
		"""
		if self.filters is None:
			# This query is already unsatisfiable and adding more constrains to this won't change this
			return self
		if isinstance(filter, dict):
			for k, v in filter.items():
				self.filter(k, v)
			return self
		if self._filterHook is not None:
			try:
				r = self._filterHook(self, filter, value)
			except RuntimeError:
				self.filters = None
				return self
			if r is None:
				# The Hook did something special directly on 'self' to apply that filter,
				# no need for us to do anything
				return self
			filter, value = r
		if " " not in filter:
			# Ensure that an equality filter is explicitly postfixed with " ="
			field = filter
			op = "="
		else:
			field, op = filter.split(" ")
		if value is not None and op.lower() in {"!=", "in", "ia"}:
			if isinstance(self.filters, list):
				raise NotImplementedError("You cannot use multiple IN or != filter")
			origFilter = self.filters
			self.filters = []
			if op == "!=":
				newFilter = {k: v for k, v in origFilter.items()}
				newFilter["%s <" % field] = value
				self.filters.append(newFilter)
				newFilter = {k: v for k, v in origFilter.items()}
				newFilter["%s >" % field] = value
				self.filters.append(newFilter)
			else:  # IN filter
				if not (isinstance(value, list) or isinstance(value, tuple)):
					raise NotImplementedError("Value must be list or tuple if using IN filter!")
				for val in value:
					newFilter = {k: v for k, v in origFilter.items()}
					op = "=" if op.lower() == "in" else "AC"
					newFilter["%s %s" % (field, op)] = val
					self.filters.append(newFilter)
		elif filter and value is not __undefinedC__:
			if isinstance(self.filters, list):
				for singeFilter in self.filters:
					singeFilter["%s %s" % (field, op)] = value
			else:  # It must be still a dict (we tested for None already above)
				self.filters["%s %s" % (field, op)] = value
			if op in {"<", "<=", ">", ">="} and len(self.orders) > 0 and self.orders[0][0] != field:
				self.order((field, ASCENDING), *self.orders)

		else:
			raise NotImplementedError("Incorrect call to query.filter()!")
		return (self)

	def order(self, *orderings):
		"""
			Specify a query sorting.

			Resulting entities will be sorted by the first property argument, then by the
			second, and so on.

			The following example

			.. code-block:: python

				query = Query( "Person" )
				query.order( "bday", ( "age", Query.DESCENDING ) )

			sorts every Person in order of their birthday, starting with January 1.
			People with the same birthday are sorted by age, oldest to youngest.

			The direction for each sort property may be provided; if omitted, it
			defaults to ascending.

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
			e.g. if bob['id'] is an int and fred['id'] is a string - the entities will be
			grouped first by the property type, then sorted within type. No attempt is
			made to compare property values across types.

			Raises BadArgumentError if any argument is of the wrong format.

			:param orderings: The properties to sort by, in sort order.\
			Each argument may be either a string or (string, direction) 2-tuple.
			:param orderings: str | tuple

			:returns: Returns the query itself for chaining.
			:rtype: server.db.Query
		"""
		newOrderings = []
		hasKeyOrdering = False
		lastOrdering = ASCENDING
		for reqOrder in orderings:
			if isinstance(reqOrder, str):
				fieldName = reqOrder
				newOrderings.append((fieldName, ASCENDING))
				if fieldName == KEY_SPECIAL_PROPERTY:
					hasKeyOrdering = True
				lastOrdering = ASCENDING
			elif isinstance(reqOrder, tuple):
				fieldName = reqOrder[0]
				newOrderings.append((fieldName, reqOrder[1]))
				if fieldName == KEY_SPECIAL_PROPERTY:
					hasKeyOrdering = True
				lastOrdering = reqOrder[1]
			else:
				raise BadArgumentError("Dont know what to do with %s" % type(fieldName), )
		if self._orderHook is not None:
			try:
				orderings = self._orderHook(self, newOrderings)
			except RuntimeError:
				self.filters = None
				return self
			if orderings is None:
				return self
		if self.filters is None:
			return
		if not hasKeyOrdering:
			newOrderings.append((KEY_SPECIAL_PROPERTY, lastOrdering))
		self.orders = newOrderings
		return self

	def setCursor(self, startCursor, endCursor=None):
		"""
			Sets the start cursor for this query.

			The result set will only include results behind that cursor.
			The cursor is generated by an earlier query with exactly the same configuration.

			Its safe to use client-supplied cursors, a cursor can't be abused to access entities
			which don't match the current filters.

			:param cursor: The cursor key to set to the Query.
			:type cursor: str | datastore_query.Cursor

			:returns: Returns the query itself for chaining.
			:rtype: server.db.Query
		"""
		if isinstance(startCursor, str) and startCursor.startswith("h-"):
			self._startCursor = bytes.fromhex(startCursor[2:])
		else:
			self._startCursor = startCursor
		self._endCursor = endCursor
		return self

		def untrustedCursorHelper(cursor):
			splits = str(cursor).split("_")
			if len(splits) != 3:
				raise InvalidCursorError("Invalid cursor format")
			res = "%s_%s" % (splits[0], splits[1])
			if not utils.hmacVerify(res, splits[2]):
				raise InvalidCursorError("Cursor signature invalid")
			return res

		if isinstance(startCursor, str):
			startCursor = untrustedCursorHelper(startCursor)
		elif isinstance(startCursor, list) or startCursor is None:
			pass
		else:
			raise ValueError("startCursor must be String, datastore_query.Cursor or None")
		if endCursor is not None:
			if isinstance(endCursor, str):
				endCursor = untrustedCursorHelper(endCursor)
			elif isinstance(endCursor, list) or endCursor is None:
				pass
			else:
				raise ValueError("endCursor must be String, datastore_query.Cursor or None")
		self._startCursor = startCursor
		self._endCursor = endCursor
		return self

	def limit(self, amount):
		"""
			Sets the query limit to *amount* entities in the result.

			Specifying an amount of 0 disables the limit (use with care!).

			:param amount: The maximum number of entities.
			:type amount: int

			:returns: Returns the query itself for chaining.
			:rtype: server.db.Query
		"""
		self.amount = amount
		return self

	def isKeysOnly(self):
		"""
			Returns True if this query is configured as *keys only*, False otherwise.

			:rtype: bool
		"""
		return (self.datastoreQuery.IsKeysOnly())

	def getQueryOptions(self):
		"""
			Returns a datastore_query.QueryOptions for the current instance.

			:rtype: datastore_query.QueryOptions
		"""
		return (self.datastoreQuery.GetQueryOptions())

	def getQuery(self):
		"""
			Returns a datastore_query.Query for the current instance.

			:rtype: datastore_query.Query
		"""
		return (self.datastoreQuery.GetQuery())

	def getOrder(self):
		"""
			Gets a datastore_query.Order for the current instance.

			:returns: The sort orders set on the current query, or None.
			:rtype: datastore_query.Order or None
		"""
		if self.datastoreQuery is None:
			return (None)

		return (self.datastoreQuery.GetOrder())

	def getFilter(self):
		"""
			Returns the filters applied to the current query as dictionary.

			:returns: Filter as dictionary.
			:rtype: dict
		"""
		return self.filters

	def getOrders(self):
		"""
			Returns a list of orders applied to this query.

			Every element in the list returned (if any), is a tuple of (property,direction).

			Property is the name of the property used to sort, direction a bool
			(false => ascending, True => descending).

			:returns: list of orderings, in tuples (property,direction).
			:rtype: list
		"""
		try:
			order = self.datastoreQuery.__orderings
			return ([(prop, dir) for (prop, dir) in order])
		except:
			return ([])

	def getCursor(self, serializeForUntrustedUse=False):
		"""
			Get a valid cursor from the last run of this query.

			The source of this cursor varies depending on what the last call was:
			- :func:`server.db.Query.run`: A cursor that points immediatelly behind the\
			last result pulled off the returned iterator.
			- :func:`server.db.Query.get`:: A cursor that points immediatelly behind the\
			last result in the returned list.
			- :func:`server.db.Query.count`: A cursor that points immediatelly behind the\
			last result counted.

			:returns: A cursor that can be used in subsequent query requests.
			:rtype: datastore_query.Cursor

			:raises: :exc:`AssertionError` if the query has not yet been run or cannot be compiled.
		"""
		return self.lastCursor
		if not isinstance(self.filters, dict):
			# Either a multi-query or an unsatisfiable query
			return None
		if not self._lastEntry:
			# We did not run yet
			return None

		res = []
		for fieldPath, direction in self.orders:
			if fieldPath == KEY_SPECIAL_PROPERTY:
				res.append("%s/%s" % (self._lastEntry.collection, self._lastEntry.name))
			else:
				res.append(_valueFromEntry(self._lastEntry, fieldPath))
		if serializeForUntrustedUse:
			# We could simply fallback for a normal hash here as we sign it later again
			hmacSigData = utils.hmacSign(res)
			res = "%s_%s" % (self._lastEntry.name, hmacSigData)
			hmacFullSig = utils.hmacSign(res)
			res += "_" + hmacFullSig
		return res

	def getKind(self):
		"""
			Returns the kind of this query.

			:rtype: str
		"""
		return self.collection

	def setKind(self, newKind):
		"""
			Sets the kind of this query.

			:param newKind: New query kind.
			:type newKind: str
		"""
		if self.datastoreQuery is None:
			return
		self.datastoreQuery.__kind = newKind

	def getAncestor(self):
		"""
			Returns the ancestor of this query (if any).

			:rtype: str | None
		"""
		return (self.datastoreQuery.ancestor)


	def _runSingleFilterQuery(self, filters, amount):
		qry = __client__.query(kind=self.getKind())
		for k, v in filters.items():
			key, op = k.split(" ")
			qry.add_filter(key, op, v)
		qry.order = [x[0] if x[1]==ASCENDING else "-"+x[0] for x in self.orders]
		qryRes = qry.fetch(limit=amount, start_cursor=self._startCursor, end_cursor=self._endCursor)
		res = next(qryRes.pages)
		self.lastCursor = qryRes.next_page_token
		return res

	def run(self, limit=-1, **kwargs):
		"""
			Run this query.

			It is more efficient to use *limit* if the number of results is known.

			If queried data is wanted as instances of Skeletons, :func:`server.db.Query.fetch`
			should be used.

			:param limit: Limits the query to the defined maximum entities.
			:type limit: int

			:param kwargs: Any keyword arguments accepted by datastore_query.QueryOptions().

			:returns: An iterator that provides access to the query results iterator
			:rtype: list

			:raises: :exc:`BadFilterError` if a filter string is invalid
			:raises: :exc:`BadValueError` if a filter value is invalid.
			:raises: :exc:`BadQueryError` if an IN filter in combination with a sort order on\
			another property is provided
		"""
		if self.filters is None:
			return None
		origLimit = limit if limit != -1 else self.amount
		qryLimit = origLimit

		if self._fulltextQueryString:
			if 0 and currentTransaction:
				raise InvalidStateError("Can't run fulltextSearch inside transactions!")
			qryStr = self._fulltextQueryString
			self._fulltextQueryString = None  # Reset, so the adapter can still work with this query
			res = self.srcSkel.customDatabaseAdapter.fulltextSearch(qryStr, self)
			if not self.srcSkel.customDatabaseAdapter.fulltextSearchGuaranteesQueryConstrains:
				# Search might yield results that are not included in the listfilter
				if isinstance(self.filters, dict):  # Just one
					res = [x for x in res if _entryMatchesQuery(x, self.filters)]
				else:  # Multi-Query, must match at least one
					res = [x for x in res if any([_entryMatchesQuery(x, y) for y in self.filters])]
		elif isinstance(self.filters, list):
			# We have more than one query to run
			if self._calculateInternalMultiQueryAmount:
				qryLimit = self._calculateInternalMultiQueryAmount(qryLimit)
			res = []
			# We run all queries first (preventing multiple round-trips to the server
			for singleFilter in self.filters:
				res.append(self._runSingleFilterQuery(
					filters=singleFilter,
					amount=qryLimit))
			# Wait for the actual results to arrive and convert the protobuffs to Entries
			res = [list(x) for x in res]
			#if additionalTransactionEntries:
			#	res = [self._injectPendingWrites(
			#		entites=resultList,
			#		singleFilter=singeFilter,
			#		pendingWrites=currentTransaction["pendingChanges"][self.collection],
			#		targetAmount=qryLimit)
			#		for resultList, singeFilter in zip(res, self.filters)]
			if self._customMultiQueryMerge:
				# We have a custom merge function, use that
				res = self._customMultiQueryMerge(self, res, origLimit)
			else:
				# We must merge (and sort) the results ourself
				res = self._mergeMultiQueryResults(res)
		else:  # We have just one single query
			res = list(self._runSingleFilterQuery(self.filters, qryLimit))
			#res = [_protoMapToEntry(tmpRes.document.fields, tmpRes.document.name[__documentRootLen__:].split("/")) for
			#	   tmpRes in self._runSingleFilterQuery(
			#		filters=self.filters,
			#		transaction=currentTransaction["transactionKey"] if currentTransaction else None,
			#		amount=qryLimit + additionalTransactionEntries) if tmpRes.document.name]
			#if additionalTransactionEntries:
			#	res = self._injectPendingWrites(
			#		entites=res,
			#		singleFilter=self.filters,
			#		pendingWrites=currentTransaction["pendingChanges"][self.collection],
			#		targetAmount=qryLimit)
		if conf["viur.debug.traceQueries"]:
			kindName = self.origCollection
			orders = self.orders
			filters = self.filters
			logging.debug(
				"Queried %s with filter %s and orders %s. Returned %s results" % (kindName, filters, orders, len(res)))
		#if currentTransaction:
		#	currentTransaction["lastQueries"].append((self, res, limit))
		if res:
			self._lastEntry = res[-1]
		return res

	def fetch(self, limit=-1, **kwargs):
		"""
			Run this query and fetch results as :class:`server.skeleton.SkelList`.

			This function is similar to :func:`server.db.Query.run`, but returns a
			:class:`server.skeleton.SkelList` instance instead of Entities.

			:warning: The query must be limited!

			If queried data is wanted as instances of Entity, :func:`server.db.Query.run`
			should be used.

			:param limit: Limits the query to the defined maximum entities. \
			A maxiumum value of 99 entries can be fetched at once.
			:type limit: int

			:raises: :exc:`BadFilterError` if a filter string is invalid
			:raises: :exc:`BadValueError` if a filter value is invalid.
			:raises: :exc:`BadQueryError` if an IN filter in combination with a sort order on\
			another property is provided
		"""
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		amount = limit if limit != -1 else self.amount
		if amount < 1 or amount > 100:
			raise NotImplementedError(
				"This query is not limited! You must specify an upper bound using limit() between 1 and 100")
		from viur.core.skeleton import SkelList
		res = SkelList(self.srcSkel)
		dbRes = self.run(amount)
		res.customQueryInfo = self.customQueryInfo
		if dbRes is None:
			return (res)
		for e in dbRes:
			# s = self.srcSkel.clone()
			valueCache = {}
			self.srcSkel.setValuesCache(valueCache)
			self.srcSkel.setValues(e)
			res.append(self.srcSkel.getValuesCache())
		res.getCursor = lambda: self.getCursor(True)
		return res

	def iter(self, keysOnly=False):
		"""
			Run this query and return an iterator for the results.

			The advantage of this function is, that it allows for iterating
			over a large result-set, as it hasn't have to be pulled in advance
			from the data store.

			The disadvantage is, that is supports no caching yet.

			This function intentionally ignores a limit set by :func:`server.db.Query.limit`.

			:warning: If iterating over a large result set, make sure the query supports cursors. \
			Otherwise, it might not return all results as the AppEngine doesn't maintain the view \
			for a query for more than ~30 seconds.

			:param keysOnly: If the query should be used to retrieve entity keys only.
			:type keysOnly: bool
		"""
		try:
			currentTransaction = __currentTransaction__.transactionData
		except AttributeError:
			currentTransaction = None
		# if currentTransaction:  # FIXME!
		#	raise InvalidStateError("Iter is currently not supported in transactions")
		for x in self.run(999):  # Fixme!
			yield x
		return
		if self.datastoreQuery is None:  # Noting to pull here
			raise StopIteration()
		if isinstance(self.datastoreQuery, datastore.MultiQuery) and keysOnly:
			# Wanted KeysOnly, but MultiQuery is unable to give us that.
			for res in self.datastoreQuery.Run():
				yield res.key()
		else:  # The standard-case
			stopYield = False
			lastCursor = None
			while not stopYield:
				try:
					for res in self.datastoreQuery.Run(keys_only=keysOnly):
						yield res
						try:
							lastCursor = self.datastoreQuery.GetCursor()
						except Exception as e:
							pass
					stopYield = True  # No more results to yield
				except:
					if lastCursor is None:
						stopYield = True
						logging.warning("Cannot this continue this query - it has no cursors")
						logging.warning("Not all results have been yielded!")
					else:
						logging.debug("Continuing iter() on fresh a query")
						q = self.clone()
						q.cursor(lastCursor)
						self.datastoreQuery = q.datastoreQuery
						lastCursor = None

	def get(self) -> Entity:
		"""
			Returns only the first entity of the current query.

			:returns: dict on success, or None if the result-set is empty.
			:rtype: dict
		"""
		try:
			res = list(self.run(limit=1))[0]
			return (res)
		except (IndexError, TypeError):  # Empty result-set
			return None

	def getSkel(self):
		"""
			Returns a matching :class:`server.db.skeleton.Skeleton` instance for the
			current query.

			Its only possible to use this function if this query has been created using
			:func:`server.skeleton.Skeleton.all`.

			:returns: The Skeleton or None if the result-set is empty.
			:rtype: :class:`server.skeleton.Skeleton`
		"""
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		res = self.get()
		if res is None:
			return (None)
		# s = self.srcSkel.clone()
		self.srcSkel.setValues(res)
		return self.srcSkel

	def count(self, limit=1000, **kwargs):
		"""
			Returns the number of entities that this query matches.

			:param limit: Limits the query to the defined maximum entities count.\
			If there are more results than this limit, stop short and just return this number.\
			Providing this argument makes the count operation more efficient.
			:type limit: int

			:param config: Optional configuration to use for this request. This must be specified\
			as a keyword argument.
			:type config: dict

			:returns: The number of results.
			:rtype: int
			"""
		return (self.datastoreQuery.Count(limit, **kwargs))

	def clone(self, keysOnly=None):
		"""
			Returns a deep copy of the current query.

			:param keysOnly: If the query should be used to retrieve entity keys only\
			in the new query.
			:type keysOnly: bool

			:returns: The cloned query.
			:rtype: server.db.Query
		"""
		# FIXME: Is everything covered?
		res = Query(self.getKind(), self.srcSkel)
		res.limit(self.amount)
		res.filters = deepcopy(self.filters)
		res.orders = deepcopy(self.orders)
		res._fulltextQueryString = self._fulltextQueryString
		return res

	def __repr__(self):
		return "<db.Query on %s with filters %s and orders %s>" % (self.collection, self.filters, self.orders)


class GenericDatabaseError(Exception):
	pass


class InvalidStateError(GenericDatabaseError):
	pass


class InvalidCursorError(GenericDatabaseError):
	pass


class TimeoutError(GenericDatabaseError):
	pass


def _beginTransaction(readOnly: bool = False):
	try:
		currentTransaction = __currentTransaction__.transactionData
		if currentTransaction:
			__currentTransaction__.transactionData = None
			raise InvalidStateError("There was already another transaction running (which has now been discarded)")
	except AttributeError:
		pass
	rwMode = common_pb2.TransactionOptions.ReadWrite() if not readOnly else common_pb2.TransactionOptions.ReadOnly()
	beginTransactionRequest = firestore_pb2.BeginTransactionRequest(
		database=__database__,
		options=common_pb2.TransactionOptions(read_write=rwMode))
	result = __firestoreStub__.BeginTransaction(beginTransactionRequest)
	__currentTransaction__.transactionData = {
		"transactionKey": result.transaction,
		"pendingChanges": {},
		"lastQueries": [],
		"transactionSuccessMarker": None,
		"startTime": datetime.now()
	}


def _commitTransaction():
	try:
		currentTransaction = __currentTransaction__.transactionData
	except AttributeError:
		currentTransaction = None
	if not currentTransaction:
		raise InvalidStateError("There is currently no transaction to commit.")
	if datetime.now() - currentTransaction["startTime"] > timedelta(seconds=65):
		# While firestore supports transactions for up to 270 Seconds, we limit this down to 60 as
		# frondend-requests can't run longer anyway, longer running transactions are likely to fail anyway and
		# we defer task exceution from transactions for only 90 seconds and we have to gurantee that we apply long
		# before this (or never)
		raise TimeoutError()
	writes = []
	for collection, changeMap in currentTransaction["pendingChanges"].items():
		for name, entry in changeMap.items():
			if entry is None:
				writes.append(write_pb2.Write(delete="%s%s/%s" % (__documentRoot__, collection, name)))
			else:
				documentPb = document_pb2.Document(
					name="%s%s/%s" % (__documentRoot__, entry.collection, entry.name),
					fields={k: _pythonValToProtoValue(v) for k, v in entry.items()})
				writes.append(
					write_pb2.Write(update=documentPb, update_mask=common_pb2.DocumentMask(field_paths=entry.keys())))
	commitRequest = firestore_pb2.CommitRequest(database=__database__, transaction=currentTransaction["transactionKey"],
												writes=writes)
	result = __firestoreStub__.Commit(commitRequest)
	lastQueries = currentTransaction["lastQueries"]
	__currentTransaction__.transactionData = None
	for qry, res, limit in lastQueries:
		newRes = qry.run(limit=limit)
		if res != newRes:
			logging.error("Query mismatch after transaction!")
			logging.error(qry)
			logging.error(res)
			logging.error(newRes)
			raise AssertionError("Query mismatch after transaction!")
		else:
			logging.info("Query-Match from transaction :) %s" % (qry,))


def _rollbackTransaction():
	try:
		currentTransaction = __currentTransaction__.transactionData
	except AttributeError:
		currentTransaction = None
	if not currentTransaction:
		raise InvalidStateError("There is currently no transaction to rollback.")
	rollbackRequest = firestore_pb2.RollbackRequest(database=__database__,
													transaction=currentTransaction["transactionKey"])
	result = __firestoreStub__.Rollback(rollbackRequest)
	__currentTransaction__.transactionData = None


def IsInTransaction():
	print("IsInTransaction: %s" % __client__.transaction().current() is not None)
	return __client__.transaction().current() is not None


def acquireTransactionSuccessMarker() -> str:
	"""
		Generates a token that will be written to the firestore (under "viur-transactionmarker") if the transaction
		completes successfully. Currently only used by deferredTasks to check if the task should actually execute
		or if the transaction it was created in failed.
	:return: Name of the entry in viur-transactionmarker
	"""
	try:
		currentTransaction = __currentTransaction__.transactionData
		assert currentTransaction
	except (AttributeError, AssertionError):
		raise InvalidStateError("acquireTransactionSuccessMarker cannot be called outside an transaction")
	if not currentTransaction["transactionSuccessMarker"]:
		e = Entity("viur-transactionmarker")
		e["creationdate"] = datetime.now()
		Put(e)
		currentTransaction["transactionSuccessMarker"] = e.name
	return currentTransaction["transactionSuccessMarker"]


def RunInTransaction(callee, *args, **kwargs):
	with __client__.transaction():
		res = callee(*args, **kwargs)
	return res


def RunInTransactionCustomRetries(*args, **kwargs):
	raise NotImplementedError(
		"Use RunInTransaction instead. Crossgroup transactions are now the default and can't be turned off")


RunInTransactionOptions = RunInTransactionCustomRetries

AllocateIdsAsync = NotImplementedError  # datastore.AllocateIdsAsync
AllocateIds = NotImplementedError  # datastore.AllocateIds
# RunInTransaction = NotImplementedError  # datastore.RunInTransaction
# RunInTransactionCustomRetries = NotImplementedError  # datastore.RunInTransactionCustomRetries
# RunInTransactionOptions = NotImplementedError  # datastore.RunInTransactionOptions
TransactionOptions = NotImplementedError  # datastore_rpc.TransactionOptions

# Key = NotImplementedError  # datastore_types.Key
Key = __client__.key

## Errors ##
Error = NotImplementedError  # datastore_errors.Error
BadValueError = NotImplementedError  # datastore_errors.BadValueError
BadPropertyError = NotImplementedError  # datastore_errors.BadPropertyError
BadRequestError = NotImplementedError  # datastore_errors.BadRequestError
EntityNotFoundError = NotImplementedError  # datastore_errors.EntityNotFoundError
BadArgumentError = NotImplementedError  # datastore_errors.BadArgumentError
QueryNotFoundError = NotImplementedError  # datastore_errors.QueryNotFoundError
TransactionNotFoundError = NotImplementedError  # datastore_errors.TransactionNotFoundError
Rollback = NotImplementedError  # datastore_errors.Rollback
TransactionFailedError = NotImplementedError  # datastore_errors.TransactionFailedError
BadFilterError = NotImplementedError  # datastore_errors.BadFilterError
BadQueryError = NotImplementedError  # datastore_errors.BadQueryError
BadKeyError = NotImplementedError  # datastore_errors.BadKeyError
InternalError = NotImplementedError  # datastore_errors.InternalError
NeedIndexError = NotImplementedError  # datastore_errors.NeedIndexError
ReferencePropertyResolveError = NotImplementedError  # datastore_errors.ReferencePropertyResolveError
Timeout = NotImplementedError  # datastore_errors.Timeout
CommittedButStillApplying = NotImplementedError  # datastore_errors.CommittedButStillApplying

DatastoreQuery = NotImplementedError  # datastore.Query
MultiQuery = NotImplementedError  # datastore.MultiQuery
Cursor = NotImplementedError  # datastore_query.Cursor
# IsInTransaction = NotImplementedError  # datastore.IsInTransaction

# Consts
KEY_SPECIAL_PROPERTY = "__key__"  # datastore_types.KEY_SPECIAL_PROPERTY
ASCENDING = 2
DESCENDING = 3

__all__ = [PutAsync, Put, GetAsync, Get, DeleteAsync, Delete, AllocateIdsAsync, AllocateIds, RunInTransaction,
		   RunInTransactionCustomRetries, RunInTransactionOptions, TransactionOptions,
		   Error, BadValueError, BadPropertyError, BadRequestError, EntityNotFoundError, BadArgumentError,
		   QueryNotFoundError, TransactionNotFoundError, Rollback,
		   TransactionFailedError, BadFilterError, BadQueryError, BadKeyError, BadKeyError, InternalError,
		   NeedIndexError, ReferencePropertyResolveError, Timeout,
		   CommittedButStillApplying, Entity, Query, DatastoreQuery, MultiQuery, Cursor, KEY_SPECIAL_PROPERTY,
		   ASCENDING, DESCENDING, IsInTransaction]
