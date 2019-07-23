# -*- coding: utf-8 -*-
# from google.appengine.api import datastore, datastore_types, datastore_errors
# from google.appengine.datastore import datastore_query, datastore_rpc
# from google.appengine.api import memcache
# from google.appengine.api import search
from server.config import conf
from server import utils
import logging, threading
from google.cloud import firestore
from google.cloud.firestore_v1beta1 import _helpers
from google.cloud.firestore_v1beta1 import field_path as field_path_module
from google.cloud.firestore_v1beta1.proto import common_pb2
from google.cloud.firestore_v1beta1.watch import Watch
from google.api_core import exceptions
from google.cloud import firestore
from google.cloud.firestore_v1.proto import firestore_pb2_grpc
from google.cloud.firestore_v1.proto import firestore_pb2
from google.cloud.firestore_v1.proto import query_pb2
from google.cloud.firestore_v1.types import Value as FirestoreValue
from google.cloud.firestore_v1.proto import document_pb2, common_pb2
from google.cloud.firestore_v1._helpers import encode_value, encode_dict, pbs_for_set_with_merge
from google.cloud.firestore_v1beta1.gapic import enums
from google.cloud.firestore_v1.proto import write_pb2
# google_dot_cloud_dot_firestore__v1_dot_proto_dot_write__pb2._WRITE
from google.protobuf.pyext._message import MessageMapContainer as FirestoreMessageMapContainer
from google.api_core import grpc_helpers
from grpc._channel import _Rendezvous as GrpcRendezvousError
from grpc import StatusCode as GrpcStatusCode
from pprint import pprint
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
from datetime import datetime
from typing import Union, Tuple, List, Dict, Iterable, Any
from time import time
import google.auth
from functools import partial
from server import request

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
__channel__ = grpc_helpers.create_channel("firestore.googleapis.com:443", scopes=__OauthScopesFirestore__)
__firestoreStub__ = firestore_pb2_grpc.FirestoreStub(channel=__channel__)


## Custom Datatypes


class Entity(dict):  # datastore.Entity
	"""
		Wraps ``datastore.Entity`` to prevent trying to add a string with more than 500 chars
		to an index and providing a camelCase-API.
	"""
	__slots__ = ["collection", "name"]

	def __init__(self, collection, name=None, preFill=None):
		if preFill:
			super(Entity, self).__init__(**preFill)
		else:
			super(Entity, self).__init__()
		self.collection = collection
		self.name = name

	def _fixUnindexedProperties(self):
		"""
			Ensures that no property with strlen > 500 makes it into the index.
		"""
		unindexed = list(self.getUnindexedProperties())
		for k, v in self.items():
			if isinstance(v, str) and len(v) >= 500 and not k in unindexed:
				logging.warning("Your property %s cant be indexed!" % k)
				unindexed.append(k)
			elif isinstance(v, list) or isinstance(v, tuple()):
				if any([isinstance(x, str) and len(x) >= 500 for x in v]) and not k in unindexed:
					logging.warning("Your property %s cant be indexed!" % k)
					unindexed.append(k)
		self.set_unindexed_properties(unindexed)

	def isSaved(self):
		"""
			Returns True if this entity has been saved to the data store.

			:rtype: bool
		"""
		return (self.is_saved())

	def entityGroup(self):
		"""
			Returns this entity's entity group as a Key.

			Note that the returned Key will be incomplete if this is a a root entity
			and its key is incomplete.
		"""
		return (self.entity_group())

	def getUnindexedProperties(self):
		"""
			Returns this entity's unindexed properties, as a frozen set of strings.
		"""
		return (self.unindexed_properties())

	def setUnindexedProperties(self, unindexed_properties):
		"""
			Sets the list of unindexed properties.

			Properties listed here are *not* saved in an index;
			its impossible to use them in a query filter / sort.

			But it saves one db-write op per property listed here.
		"""
		self.set_unindexed_properties(unindexed_properties)

	def __setitem__(self, name, value):
		"""
			Implements the [] operator. Used to set property value(s).

			:param name: Name of the property to set.
			:type name: str
			:param value: Any value to set tot the property.

			:raises: :exc:`BadPropertyError` if the property name is the \
			empty string or not a string.
			:raises: :exc:`BadValueError` if the value is not a supported type.
		"""
		if isinstance(value, list) or isinstance(value, tuple):
			# We cant store an empty list, so we catch any attempts
			# and store None. As "does not exists" queries aren't
			# possible anyway, this makes no difference
			if len(value) == 0:
				value = None
		super(Entity, self).__setitem__(name, value)

	def set(self, key, value, indexed=True):
		"""
			Sets a property.

			:param key: key of the property to set.
			:type key: str
			:param value: Any value to set tot the property.

			:param indexed: Defines if the value is indexed.
			:type indexed: bool

			:raises: :exc:`BadPropertyError` if the property name is the \
			empty string or not a string.
			:raises: :exc:`BadValueError` if the value is not a supported type.
		"""
		# unindexed = list(self.getUnindexedProperties())

		# if not indexed and not key in unindexed:
		#	unindexed.append(key)
		#	self.setUnindexedProperties(unindexed)
		# elif indexed and key in unindexed:
		#	unindexed.remove(key)
		#	self.setUnindexedProperties(unindexed)

		self[key] = value

	@staticmethod
	def FromDatastoreEntity(entity):
		"""
			Converts a datastore.Entity into a :class:`db.server.Entity`.

			Required, as ``datastore.Get()`` always returns a datastore.Entity
			(and it seems that currently there is no valid way to change that).
		"""
		res = Entity(entity.kind(), parent=entity.key().parent(), _app=entity.key().app(),
					 name=entity.key().name(), id=entity.key().id(),
					 unindexed_properties=entity.unindexed_properties(),
					 namespace=entity.namespace())
		res.update(entity)
		return (res)

	def __eq__(self, other):
		if not isinstance(other, Entity):
			return False
		return self.collection == other.collection and self.name == other.name and super(Entity, self).__eq__(other)

	def __repr__(self):
		other = self.copy()
		other["__key__"] = "%s/%s" % (self.collection, self.name)
		return other.__repr__()


## Helper functions for dealing with protobuffs etc.

_generateNewId = partial(utils.generateRandomString, length=20)


def _protoValueToPythonVal(value: FirestoreValue) -> \
		Union[None, bool, int, float, list, dict, str, bytes, datetime, Tuple[float, float]]:
	"""
	Constructs a native python type from it's google.cloud.firestore_v1.types.Value instance

	:param value: The google.cloud.firestore_v1.types.Value to parse
	:return: The native Python object for that value
	"""
	valType = value.WhichOneof("value_type")
	if valType in {"boolean_value", "integer_value", "double_value", "string_value", "bytes_value", "reference_value"}:
		return getattr(value, valType)
	elif valType == "null_value":
		return None
	elif valType == "timestamp_value":
		return datetime.fromtimestamp(value.timestamp_value.seconds)
	elif valType == "array_value":
		return [_protoValueToPythonVal(element) for element in value.array_value.values]
	elif valType == "map_value":
		return {key: _protoValueToPythonVal(value) for key, value in value.map_value.fields.items()}
	elif valType == "geo_point_value":
		return (value.geo_point_value.latitude, value.geo_point_value.longitude)
	else:
		raise ValueError("Value-Type '%s'not supported" % valType)


def _protoMapToEntry(protBufFields: FirestoreMessageMapContainer, keyPath: Tuple[str, str]) -> Entity:
	collection, name = keyPath
	return Entity(collection, name, {key: _protoValueToPythonVal(value) for key, value in protBufFields.items()})


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


def Put(entities: Union[Entity, List[Entity]], **kwargs) -> None:
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
	# if currentTransaction:
	#	raise NotImplementedError()  # FIXME: We must enqueue Writes to the transaction instead...
	if isinstance(entities, list):  # FIXME: Use a WriteBatch instead
		for x in entities:
			Put(x)
	if not entities.name:
		# This will be an add
		entities.name = _generateNewId()
		isAdd = True
	documentPb = document_pb2.Document(name="%s%s/%s" % (__documentRoot__, entities.collection, entities.name),
									   fields=encode_dict(entities))
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


def Get(keys: Union[Tuple[str, str], List[Tuple[str, str]]], **kwargs) -> Union[None, Entity, List[Entity]]:
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


def GetOrInsert(key: Tuple[str, str], **kwargs):
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
			obj = Entity(collection=key[0], name=key[1])
			for k, v in kwargs.items():
				obj[k] = v
			Put(obj)
		return obj

	if IsInTransaction():
		return txn(key)
	return RunInTransaction(txn, key)

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


def Delete(keys: Union[Tuple[str, str], List[Tuple[str, str]]], **kwargs) -> None:
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

	operatorMap = {
		"<": enums.StructuredQuery.FieldFilter.Operator.LESS_THAN,
		"<=": enums.StructuredQuery.FieldFilter.Operator.LESS_THAN_OR_EQUAL,
		"=": enums.StructuredQuery.FieldFilter.Operator.EQUAL,
		">=": enums.StructuredQuery.FieldFilter.Operator.GREATER_THAN_OR_EQUAL,
		">": enums.StructuredQuery.FieldFilter.Operator.GREATER_THAN,
		"AC": enums.StructuredQuery.FieldFilter.Operator.ARRAY_CONTAINS,
	}

	# Fixme: Typing for Skeleton-Class we can't import here?
	def __init__(self, collection: str, srcSkelClass: Union[None, Any] = None, *args, **kwargs):
		super(Query, self).__init__()
		self.collection = collection
		self.srcSkel = srcSkelClass
		self.filters: Union[None, Dict[str: Any], List[Dict[str: Any]]] = {}
		self.orders: List[Tuple[str, enums.StructuredQuery.Direction]] = [(KEY_SPECIAL_PROPERTY, ASCENDING)]
		self.amount: int = 30
		self._filterHook = None
		self._orderHook = None
		self._origCursor = None
		self._customMultiQueryMerge = None  # Sometimes, the default merge functionality from MultiQuery is not sufficient
		self._calculateInternalMultiQueryAmount = None  # Some (Multi-)Queries need a different amount of results per subQuery than actually returned
		self.customQueryInfo = {}  # Allow carrying custom data along with the query. Currently only used by spartialBone to record the guranteed correctnes
		self.origCollection = collection

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
		from server.bones import baseBone, relationalBone
		if "id" in filters:
			self.datastoreQuery = None
			logging.error("Filtering by id is no longer supported. Use key instead.")
			return self
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		if self.filters is None:  # This query is allready unsatifiable and adding more constrains to this wont change this
			return self
		skel = self.srcSkel
		if skel.searchIndex and "search" in filters:  # We perform a Search via Google API - all other parameters are ignored
			try:
				searchRes = search.Index(name=skel.searchIndex).search(
					query=search.Query(query_string=filters["search"], options=search.QueryOptions(limit=25)))
			except search.QueryError:  # We cant parse the query, treat it as verbatim
				qstr = u"\"%s\"" % filters["search"].replace(u"\"", u"")
				try:
					searchRes = search.Index(name=skel.searchIndex).search(
						query=search.Query(query_string=qstr, options=search.QueryOptions(limit=25)))
				except search.QueryError:  # Still cant parse it
					searchRes = []
			tmpRes = [datastore_types.Key(encoded=x.doc_id[2:]) for x in searchRes]
			if tmpRes:
				filters = []
				for x in tmpRes:
					filters.append(datastore.Query(self.getKind(), {"%s =" % datastore_types.KEY_SPECIAL_PROPERTY: x}))
				self.datastoreQuery = datastore.MultiQuery(filters, ())
			else:
				self.datastoreQuery = None
			return (self)
		# bones = [ (getattr( skel, key ), key) for key in dir( skel ) if not "__" in key and isinstance( getattr( skel, key ) , baseBone ) ]
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
		if "search" in filters and filters["search"]:
			if isinstance(filters["search"], list):
				taglist = ["".join([y for y in str(x).lower() if y in conf["viur.searchValidChars"]]) for x in
						   filters["search"]]
			else:
				taglist = ["".join([y for y in str(x).lower() if y in conf["viur.searchValidChars"]]) for x in
						   str(filters["search"]).split(" ")]
			assert not isinstance(self.datastoreQuery,
								  datastore.MultiQuery), "Searching using viur-tags is not possible on a query that already uses an IN-filter!"
			origFilter = self.datastoreQuery
			queries = []
			for tag in taglist[:30]:  # Limit to max 30 keywords
				q = datastore.Query(kind=origFilter.__kind)
				q["viur_tags"] = tag
				queries.append(q)
			self.datastoreQuery = datastore.MultiQuery(queries, origFilter.__orderings)
			for k, v in origFilter.items():
				self.datastoreQuery[k] = v
		if "cursor" in filters and filters["cursor"] and filters["cursor"].lower() != "none":
			self.cursor(filters["cursor"])
		if "amount" in filters and str(filters["amount"]).isdigit() and int(filters["amount"]) > 0 and int(
				filters["amount"]) <= 100:
			self.limit(int(filters["amount"]))
		if "postProcessSearchFilter" in dir(skel):
			skel.postProcessSearchFilter(self, filters)
		return (self)

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

	def ancestor(self, ancestor):
		"""
			Sets an ancestor for this query.

			This restricts the query to only return result entities that are descended
			from a given entity. In other words, all of the results will have the
			ancestor as their parent, or parent's parent, and so on.

			Raises BadArgumentError or BadKeyError if parent is not an existing Entity
			or Key in the data store.

			:param ancestor: Entity or Key. The key must be complete.
			:type ancestor: server.db.Entity | Key

			:returns: Returns the query itself for chaining.
			:rtype: server.db.Query
		"""
		self.datastoreQuery.Ancestor(ancestor)
		return (self)

	def cursor(self, cursor, endCursor=None):
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
		if isinstance(cursor, str):
			cursor = datastore_query.Cursor(urlsafe=cursor)
		elif isinstance(cursor, datastore_query.Cursor) or cursor == None:
			pass
		else:
			raise ValueError("Cursor must be String, datastore_query.Cursor or None")
		if endCursor is not None:
			if isinstance(endCursor, str):
				endCursor = datastore_query.Cursor(urlsafe=endCursor)
			elif isinstance(cursor, datastore_query.Cursor) or endCursor == None:
				pass
			else:
				raise ValueError("endCursor must be String, datastore_query.Cursor or None")

		qo = self.datastoreQuery.__query_options
		self.datastoreQuery.__query_options = datastore_query.QueryOptions(keys_only=qo.keys_only,
																		   produce_cursors=qo.produce_cursors,
																		   start_cursor=cursor,
																		   end_cursor=endCursor or qo.end_cursor,
																		   projection=qo.projection)
		self._origCursor = cursor
		return (self)

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
		if self.datastoreQuery is None:
			return (None)
		elif isinstance(self.datastoreQuery, MultiQuery):
			res = []
			for qry in getattr(self.datastoreQuery, "_MultiQuery__bound_queries"):
				res.append({k: v for (k, v) in qry.items()})
			return res
		return ({k: v for (k, v) in self.datastoreQuery.items()})

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

	def getCursor(self):
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
		if self.datastoreQuery is None:
			return (None)

		return (self.datastoreQuery.GetCursor())

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

	def _buildFilterProtoBuff(self, filters: dict) -> google.cloud.firestore_v1.types.StructuredQuery.Filter:
		"""
			Construct a filter protobuff for all constrains in filters dict.
			If filters is an empty dict, we can simply return none (as no constrains should be applied).
			If it's a single constrain, we simply return a FieldFilter, otherwise we return a Composite Filter
			with a list of corresponding FieldFilters.

		"""

		def mkFilterPb(key, value):
			field, opcode = key.split(" ")
			filter_pb = query_pb2.StructuredQuery.FieldFilter(
				field=query_pb2.StructuredQuery.FieldReference(field_path=field),
				op=self.operatorMap[opcode],
				value=encode_value(value),
			)
			return query_pb2.StructuredQuery.Filter(field_filter=filter_pb)

		num_filters = len(filters)
		if num_filters == 0:
			return None
		elif num_filters == 1:
			# Fixme: What's the fastest method of getting the single key/value pair from an dict without modifying it
			key, val = filters.copy().popitem()
			return mkFilterPb(key, val)
		else:
			composite_filter = query_pb2.StructuredQuery.CompositeFilter(
				op=enums.StructuredQuery.CompositeFilter.Operator.AND,
				filters=[mkFilterPb(key, val) for key, val in filters.items()],
			)
			return query_pb2.StructuredQuery.Filter(composite_filter=composite_filter)

	def _buildOrderProtoBuff(self, orders: Union[None, List[Tuple[str, int]]], filters: dict) \
			-> Union[None, Tuple[query_pb2.StructuredQuery.Order]]:
		"""
			Constructs an StructuredQuery.Order Protobuff that corresponds to the orders requested.
			Care must be taken if we sort by a field that's also used in an IN Query
		"""
		if not orders:
			return None
		return tuple(query_pb2.StructuredQuery.Order(
			field=query_pb2.StructuredQuery.FieldReference(field_path=field),
			direction=direction) for field, direction in orders if "%s =" % field not in filters)

	def _buildProtoBuffForQuery(self, filters, orders, limit) -> google.cloud.firestore_v1.types.StructuredQuery:
		"""
			Constructs the corresponding protobuffer for the query given in by filters, orders and limit

		Returns:
			google.cloud.firestore_v1beta1.types.StructuredQuery: The
			query protobuf.
		"""
		projection = None  # self._normalize_projection(self._projection)
		orders = None  # self._normalize_orders()
		start_at = None  # self._normalize_cursor(self._start_at, orders)
		end_at = None  # self._normalize_cursor(self._end_at, orders)

		query_kwargs = {
			"select": projection,
			"from": [
				query_pb2.StructuredQuery.CollectionSelector(
					collection_id=self.collection
				)
			],
			"where": self._buildFilterProtoBuff(filters),
			"order_by": self._buildOrderProtoBuff(self.orders, filters),
			"start_at": None,  # cursor_pb(start_at),
			"end_at": None  # _cursor_pb(end_at),
		}
		# if self._offset is not None:
		#	query_kwargs["offset"] = self._offset
		# if self._limit is not None:
		#	query_kwargs["limit"] = wrappers_pb2.Int32Value(value=self._limit)
		return query_pb2.StructuredQuery(**query_kwargs)

	def _runSingleFilterQuery(self, filters: dict, transaction: Union[None, bytes], amount: int) -> Iterable[dict]:
		"""
			Runs a single query with the given filter dict.
			Orders, Limits etc are taken from self.
		:param filters:
		:return:
		"""
		protoBuff = self._buildProtoBuffForQuery(filters, self.orders, amount)
		req = firestore_pb2.RunQueryRequest(
			parent=__documentRoot__[:-1],
			structured_query=protoBuff,
			transaction=transaction)
		return __firestoreStub__.RunQuery(req)

	def _mergeMultiQueryResults(self, inputRes: List[List[Entity]]) -> List[Entity]:
		"""
			Merge the lists of entries into a single list; removing duplicates and restoring sort-order
		:param inputRes: Nested Lists of Entries returned by each individual query run
		:return: Sorted & deduplicated list of entries
		"""
		seenKeys = set()
		res = []
		for subList in inputRes:
			for entry in subList:
				key = "%s/%s" % (entry.collection, entry.name)
				if key in seenKeys:
					continue
				seenKeys.add(key)
				res.append(entry)
		# Fixme: What about filters that mix different inequality filters - we'll now simply ignore any implicit sortorder
		return self._resortResult(res, {}, self.orders)

	def _injectPendingWrites(self, entites: List[Entity], singleFilter: Dict[str, any],
							 pendingWrites: Dict[str, Entity], targetAmount: int) -> List[Entity]:
		"""
			If we run a query inside a transaction, it might return stale entries as we might already have pending
			writes which the firestore doesn't yet know about (as we can only write once on commit).
			So we have to validate that
				- Each entry returned still does match our filters
				- Is in the correct position in the result (a pending write may will cause a shift if the field were
				sorting by has changed
				- No entry that is marked for delete is returned
				- Any new entry (either changed or freshly added) which would have been returned if firestore already
				knew about it is also appended

			What we do: We append all new Entries to the list of returned entries (or update the entry in place if it's
			changed and returned from the firestore).
			Then we'll filter the list, discarding any entry that would not match the filters anymore.
			Next, we re-sort the entries still in the list and truncate it to the len originally requested
		:param entites: List of entries returned from firestore
		:param pendingWrites: Dict of enqueued changes for that collection
		:return: Fixed list of entries as the firestore would have returned if it knew the pending changes
		"""

		def mergeWithUpdatedEntry(entry, key):
			if not key in pendingWrites:
				return entry
			return pendingWrites[key]

		# Inplace merge returned entities with our pending changelist
		tmpDict = {entry.name: mergeWithUpdatedEntry(entry, entry.name) for entry in entites}
		# Add any (maybe newly added) entry to the list
		for name, entry in pendingWrites.items():
			if name not in tmpDict:
				tmpDict[name] = entry
		# Next we reject any entry that doesn't match the query anymore
		resList = []
		ineqFilter = None
		for entry in tmpDict.values():
			if not entry:
				continue
			for filterStr, filterValue in singleFilter.items():
				field, opcode = filterStr.split(" ")
				operator = self.operatorMap[opcode]
				fieldValue = entry.get(field)
				if operator == enums.StructuredQuery.FieldFilter.Operator.EQUAL:
					if fieldValue != filterValue:  # Not equal - do not append
						break
				elif operator == enums.StructuredQuery.FieldFilter.Operator.LESS_THAN:
					ineqFilter = field
					if not fieldValue < filterValue:
						break
				elif operator == enums.StructuredQuery.FieldFilter.Operator.GREATER_THAN:
					ineqFilter = field
					if not fieldValue > filterValue:
						break
				elif operator == enums.StructuredQuery.FieldFilter.Operator.LESS_THAN_OR_EQUAL:
					ineqFilter = field
					if not fieldValue <= filterValue:
						break
				elif operator == enums.StructuredQuery.FieldFilter.Operator.GREATER_THAN_OR_EQUAL:
					ineqFilter = field
					if not fieldValue >= filterValue:
						break
				elif operator == enums.StructuredQuery.FieldFilter.Operator.ARRAY_CONTAINS:
					if not fieldValue in filterValue:
						break
			else:
				# We did not reach a break - we can include that entry
				resList.append(entry)
		# Final step: Sort and truncate to requested length
		return self._resortResult(resList, singleFilter, self.orders)[:targetAmount]

	def _resortResult(self, entities: List[Entity], filters: Dict[str, Any],
					  orders: List[Tuple[str, enums.StructuredQuery.Direction]]) -> List[Entity]:

		def getVal(src: Entity, fieldVars: Union[str, Tuple[str]], direction: enums.StructuredQuery.Direction) -> Any:
			# Descent into the target until we reach the property we're looking for
			if isinstance(fieldVars, tuple):
				for fv in fieldVars:
					if not fv in src:
						return None
					src = src[fv]
			else:
				if not fieldVars in src:
					return (str(type(None)), 0)
				src = src[fieldVars]
			# We must return this tuple because inter-type comparison isn't possible in Python3 anymore
			return (str(type(src)), src if src is not None else 0)

		# Check if we have an inequality filter which implies an sortorder
		ineqFilter = None
		for k, _ in filters.items():
			end = k[-2:]
			if "<" in end or ">" in end:
				ineqFilter = k.split(" ")[0]
				break
		if ineqFilter and (not orders or not orders[0][0] == ineqFilter):
			orders = [(ineqFilter, ASCENDING)] + (orders or [])

		for orderField, direction in orders[::-1]:
			if orderField == KEY_SPECIAL_PROPERTY:
				entities.sort(key=lambda x: x.name, reverse=direction == DESCENDING)
			else:
				entities.sort(key=partial(getVal, fieldVars=orderField, direction=direction),
							  reverse=direction == DESCENDING)

		return entities

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
		try:
			currentTransaction = __currentTransaction__.transactionData
		except AttributeError:
			currentTransaction = None
		origLimit = limit if limit != -1 else self.amount
		qryLimit = origLimit
		additionalTransactionEntries = 0
		if currentTransaction:
			# We might have to fetch more than the requested items as some items returned from the query might not
			# match the query anymore (as we have pending writes which the firestore doesn't know about yet)
			if self.collection in currentTransaction["pendingChanges"]:
				additionalTransactionEntries = len(currentTransaction["pendingChanges"][self.collection])
		if isinstance(self.filters, list):
			# We have more than one query to run
			if self._calculateInternalMultiQueryAmount:
				qryLimit = self._calculateInternalMultiQueryAmount(qryLimit)
			res = []
			# We run all queries first (preventing multiple round-trips to the server
			for singleFilter in self.filters:
				res.append(self._runSingleFilterQuery(
					filters=singleFilter,
					transaction=currentTransaction["transactionKey"] if currentTransaction else None,
					amount=qryLimit + additionalTransactionEntries))
			# Wait for the actual results to arrive and convert the protobuffs to Entries
			res = [
				[_protoMapToEntry(tmpRes.document.fields, tmpRes.document.name[__documentRootLen__:].split("/")) for tmpRes in x if
				 tmpRes.document.name]
				for x in res]
			if additionalTransactionEntries:
				res = [self._injectPendingWrites(
					entites=resultList,
					singleFilter=singeFilter,
					pendingWrites=currentTransaction["pendingChanges"][self.collection],
					targetAmount=qryLimit)
					for resultList, singeFilter in zip(res, self.filters)]
			if self._customMultiQueryMerge:
				# We have a custom merge function, use that
				res = self._customMultiQueryMerge(self, res, origLimit)
			else:
				# We must merge (and sort) the results ourself
				res = self._mergeMultiQueryResults(res)
		else:  # We have just one single query
			res = [_protoMapToEntry(tmpRes.document.fields, tmpRes.document.name[__documentRootLen__:].split("/")) for
				   tmpRes in self._runSingleFilterQuery(
					filters=self.filters,
					transaction=currentTransaction["transactionKey"] if currentTransaction else None,
					amount=qryLimit + additionalTransactionEntries) if tmpRes.document.name]
			if additionalTransactionEntries:
				res = self._injectPendingWrites(
					entites=res,
					singleFilter=self.filters,
					pendingWrites=currentTransaction["pendingChanges"][self.collection],
					targetAmount=qryLimit)
		if conf["viur.debug.traceQueries"]:
			kindName = self.origCollection
			orders = self.orders
			filters = self.filters
			logging.debug(
				"Queried %s with filter %s and orders %s. Returned %s results" % (kindName, filters, orders, len(res)))
		if currentTransaction:
			currentTransaction["lastQueries"].append((self, res))
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
		from server.skeleton import SkelList
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
		try:
			c = self.datastoreQuery.GetCursor()
			if c:
				res.cursor = c.urlsafe()
			else:
				res.cursor = None
		except (AssertionError, AttributeError):  # No Cursors available on MultiQueries ( in or != )
			# FIXME! AttributeError is always raised - need to fix cursors...
			res.cursor = None
		return (res)

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
		if currentTransaction:
			raise InvalidStateError("Iter is currently not supported in transactions")
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

	def get(self):
		"""
			Returns only the first entity of the current query.

			:returns: dict on success, or None if the result-set is empty.
			:rtype: dict
		"""
		try:
			res = list(self.run(limit=1))[0]
			return (res)
		except IndexError:  # Empty result-set
			return (None)
		except TypeError:  # Also Empty result-set
			return (None)

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
		if keysOnly is None:
			keysOnly = self.isKeysOnly()
		res = Query(self.getKind(), self.srcSkel, keys_only=keysOnly)
		res.limit(self.amount)
		for k, v in self.getFilter().items():
			res.filter(k, v)
		orders = self.getOrders()
		if len(orders) == 1:
			res.order(orders[0])
		elif len(orders) > 1:
			res.order(tuple(orders))
		return (res)

	def __repr__(self):
		return "<db.Query on %s with filters %s and orders %s>" % (self.collection, self.filters, self.orders)


class InvalidStateError(Exception):
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
	}


def _commitTransaction():
	try:
		currentTransaction = __currentTransaction__.transactionData
	except AttributeError:
		currentTransaction = None
	if not currentTransaction:
		raise InvalidStateError("There is currently no transaction to commit.")
	writes = []
	for collection, changeMap in currentTransaction["pendingChanges"].items():
		for name, entry in changeMap.items():
			if entry is None:
				writes.append(write_pb2.Write(delete="%s%s/%s" % (__documentRoot__, collection, name)))
			else:
				documentPb = document_pb2.Document(
					name="%s%s/%s" % (__documentRoot__, entry.collection, entry.name),
					fields=encode_dict(entry))
				writes.append(
					write_pb2.Write(update=documentPb, update_mask=common_pb2.DocumentMask(field_paths=entry.keys())))
	commitRequest = firestore_pb2.CommitRequest(database=__database__, transaction=currentTransaction["transactionKey"],
												writes=writes)
	result = __firestoreStub__.Commit(commitRequest)
	lastQueries = currentTransaction["lastQueries"]
	__currentTransaction__.transactionData = None
	for qry, res in lastQueries:
		newRes = qry.run()
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
	try:
		currentTransaction = __currentTransaction__.transactionData
	except AttributeError:
		currentTransaction = None
	return currentTransaction is not None


def RunInTransaction(callee, *args, **kwargs):
	_beginTransaction()
	try:
		res = callee(*args, **kwargs)
	except Exception as e:
		logging.error("Error in TXN")
		logging.exception(e)
		_rollbackTransaction()
		raise
	else:
		_commitTransaction()
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

Key = NotImplementedError  # datastore_types.Key

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
KEY_SPECIAL_PROPERTY = "__name__"  # datastore_types.KEY_SPECIAL_PROPERTY
ASCENDING = enums.StructuredQuery.Direction.ASCENDING
DESCENDING = enums.StructuredQuery.Direction.DESCENDING

__all__ = [PutAsync, Put, GetAsync, Get, DeleteAsync, Delete, AllocateIdsAsync, AllocateIds, RunInTransaction,
		   RunInTransactionCustomRetries, RunInTransactionOptions, TransactionOptions,
		   Error, BadValueError, BadPropertyError, BadRequestError, EntityNotFoundError, BadArgumentError,
		   QueryNotFoundError, TransactionNotFoundError, Rollback,
		   TransactionFailedError, BadFilterError, BadQueryError, BadKeyError, BadKeyError, InternalError,
		   NeedIndexError, ReferencePropertyResolveError, Timeout,
		   CommittedButStillApplying, Entity, Query, DatastoreQuery, MultiQuery, Cursor, KEY_SPECIAL_PROPERTY,
		   ASCENDING, DESCENDING, IsInTransaction]
