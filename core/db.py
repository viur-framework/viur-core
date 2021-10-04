# -*- coding: utf-8 -*-
from __future__ import annotations

import os

from viur.core.config import conf
from viur.core import utils
import logging
from typing import Union, Tuple, List, Dict, Any, Callable, Set, Optional
from functools import partial
from itertools import zip_longest
from copy import deepcopy
from google.cloud import datastore, exceptions
from enum import Enum
from datetime import datetime, date, time
import binascii
from dataclasses import dataclass, field
from contextvars import ContextVar

try:
	from viur import dbaccelerator
except ImportError:
	dbaccelerator = None

"""
	Tiny wrapper around *google.cloud.datastore*.

	This module provides some utility functions and a wrapper around queries with commonly needed functionality for
	relations. It also ensures that datastore access is recorded accordingly so the caching module can function
	correctly.
"""

__client__ = datastore.Client()
# The DB-Module will keep track of accessed kinds/keys in the accessLog so we can selectively flush our caches
currentDbAccessLog: ContextVar[Optional[Set[Union[KeyClass, str]]]] = ContextVar("Database-Accesslog", default=None)

# Consts
KEY_SPECIAL_PROPERTY = "__key__"
DATASTORE_BASE_TYPES = Union[None, str, int, float, bool, datetime, date, time, datastore.Key]


class SortOrder(Enum):
	Ascending = 1  # Sort A->Z
	Descending = 2  # Sort Z->A
	InvertedAscending = 3  # Fetch Z->A, then flip the results (useful in pagination to go from a start cursor backwards)
	InvertedDescending = 4  # Fetch A->Z, then flip the results (useful in pagination)


@dataclass
class QueryDefinition:
	kind: str
	filters: Dict[str, DATASTORE_BASE_TYPES]
	orders: List[Tuple[str, SortOrder]]
	distinct: Union[None, List[str]] = None
	limit: int = 30
	startCursor: Union[None, str] = None
	endCursor: Union[None, str] = None
	currentCursor: Union[None, str] = None


# Proxied Function / Classed
Entity = datastore.Entity
Key = __client__.key  # Proxy-Function
KeyClass = datastore.Key  # Expose the class also
# Get = __client__.get
# Delete = __client__.delete
AllocateIds = __client__.allocate_ids
Conflict = exceptions.Conflict
Error = exceptions.GoogleCloudError

# These will be filled from skeleton.py to avoid circular references
SkelListRef = None
SkeletonInstanceRef = None


def keyHelper(inKey: Union[KeyClass, str, int], targetKind: str,
			  additionalAllowdKinds: Union[None, List[str]] = None) -> KeyClass:
	if isinstance(inKey, str):
		try:
			decodedKey = utils.normalizeKey(KeyClass.from_legacy_urlsafe(inKey))
		except:
			decodedKey = None
		if decodedKey:  # If it did decode, don't try any further
			if decodedKey.kind != targetKind and (not additionalAllowdKinds or inKey.kind not in additionalAllowdKinds):
				raise ValueError("Kin1d mismatch: %s != %s" % (decodedKey.kind, targetKind))
			return decodedKey
		if inKey.isdigit():
			inKey = int(inKey)
		return Key(targetKind, inKey)
	elif isinstance(inKey, int):
		return Key(targetKind, inKey)
	elif isinstance(inKey, KeyClass):
		if inKey.kind != targetKind and (not additionalAllowdKinds or inKey.kind not in additionalAllowdKinds):
			raise ValueError("Kin1d mismatch: %s != %s (%s)" % (inKey.kind, targetKind, additionalAllowdKinds))
		return inKey
	else:
		raise ValueError("Unknown key type %r" % type(inKey))


def encodeKey(key: KeyClass) -> str:
	"""
		Return the given key encoded as string (mimicking the old str() behaviour of keys)
	"""
	return key.to_legacy_urlsafe().decode("ASCII")


def startAccessDataLog() -> Set[Union[KeyClass, str]]:
	"""
		Clears our internal access log (which keeps track of which entries have been accessed in the current
		request). The old set of accessed entries is returned so that it can be restored with
		:func:`server.db.popAccessData` in case of nested caching.
		:return: Set of old accessed entries
	"""
	old = currentDbAccessLog.get(set())
	currentDbAccessLog.set(set())
	return old


def popAccessData(outerAccessLog: Optional[Set[Union[KeyClass, str]]] = None) -> Set[Union[KeyClass, str]]:
	"""
		Retrieves the set of entries accessed so far. If :func:`server.db.startAccessDataLog`, it will only
		include entries that have been accessed after that call, otherwise all entries accessed in the current
		request. If you called :func:`server.db.startAccessDataLog` before, you can re-apply the old log using
		the outerAccessLog param.
		:param outerAccessLog: State of your log returned by :func:`server.db.startAccessDataLog`
		:return: Set of entries accessed
	"""
	res = currentDbAccessLog.get(set())
	currentDbAccessLog.set((outerAccessLog or set()).union(res))
	return res


def Get(keys: Union[KeyClass, List[KeyClass]]) -> Union[List[Entity], Entity, None]:
	"""
		Retrieves an entity (or a list thereof) from datastore.
		If only a single key has been given we'll return the entity or none in case the key has not been found,
		otherwise a list of all entities that have been looked up (which may be empty)
		:param keys: A datastore key (or a list thereof) to lookup
		:return: The entity (or None if it has not been found), or a list of entities.
	"""
	dataLog = currentDbAccessLog.get(set())
	if isinstance(keys, list):
		for key in keys:
			if not key.kind.startswith("viur"):
				dataLog.add(key)
		if dbaccelerator and not IsInTransaction():  # Use the fast-path fetch
			return dbaccelerator.fetchMulti(keys)
		else:
			# GetMulti does not obey orderings - results can be returned in any order. We'll need to fix this here
			resList = list(__client__.get_multi(keys))
			resList.sort(key=lambda x: keys.index(x.key) if x else -1)
			return resList
	if not keys.kind.startswith("viur"):
		dataLog.add(keys)
	if dbaccelerator and not IsInTransaction():  # Use the fast-path fetch
		return dbaccelerator.fetchMulti([keys])[0]
	else:
		return __client__.get(keys)


def Put(entity: Union[Entity, List[Entity]]):
	"""
		Save an entity in the Cloud Datastore.
		Also ensures that no string-key with an digit-only name can be used.
		:param entity: The entity to be saved to the datastore.
	"""
	dataLog = currentDbAccessLog.get(set())
	if not isinstance(entity, list):
		entity = [entity]
	for e in entity:
		if not e.key.is_partial:
			if not e.key.kind.startswith("viur"):
				dataLog.add(e.key)
			if e.key.name and e.key.name.isdigit():
				raise ValueError("Cannot store an entity with digit-only string key")
		else:
			if not e.key.kind.startswith("viur"):
				dataLog.add(e.key.kind)
	# fixUnindexableProperties(e)
	return __client__.put_multi(entities=entity)


def Delete(keys: Union[Entity, List[Entity], KeyClass, List[KeyClass]]):
	"""
		Deletes the entities with the given key(s) from the datastore.
		:param keys: A Key (or a List of Keys) to delete
	"""
	dataLog = currentDbAccessLog.get(set())
	if isinstance(keys, list):
		keys = [(x if isinstance(x, KeyClass) else x.key) for x in keys]
		for key in keys:
			if not key.kind.startswith("viur"):
				dataLog.add(key)
		return __client__.delete_multi(keys)
	else:
		if isinstance(keys, KeyClass):
			if not keys.kind.startswith("viur"):
				dataLog.add(keys)
			return __client__.delete(keys)
		else:
			if not keys.key.kind.startswith("viur"):
				dataLog.add(keys.key)
			return __client__.delete(keys.key)


def fixUnindexableProperties(entry: Entity) -> Entity:
	"""
		Recursivly walk the given Entity and add all properties to the list of unindexed properties if they contain
		a string longer than 500 bytes (which is maximum size of a string that can be indexed). The datastore would
		return an error otherwise.
	:param entry: The entity to fix (inplace)
	:return: The fixed entity
	"""
	def hasUnindexableProperty(prop):
		if isinstance(prop, dict):
			return any([hasUnindexableProperty(x) for x in prop.values()])
		elif isinstance(prop, list):
			return any([hasUnindexableProperty(x) for x in prop])
		elif isinstance(prop, (str, bytes)):
			return len(prop) >= 500
		else:
			return False

	resList = []
	for k, v in entry.items():
		if hasUnindexableProperty(v):
			if isinstance(v, dict):
				innerEntry = Entity()
				innerEntry.update(v)
				entry[k] = fixUnindexableProperties(innerEntry)
				if isinstance(v, Entity):
					innerEntry.key = v.key
			else:
				resList.append(k)
	entry.exclude_from_indexes = resList
	return entry


def _entryMatchesQuery(entry: Entity, singleFilter: dict) -> bool:
	"""
		Utility function which checks if the given entity could have been returned by a query filtering by the
		properties in singleFilter. This can be used if a list of entities have been retrieved (e.g. by a 3rd party
		full text search engine) and these have now to be checked against the filter returned by their modules
		:meth:`viur.core.prototypes.list.listFilter` method.
		:param entry: The entity which will be tested
		:param singleFilter: A dictionary containing all the filters from the query
		:return: True if the entity could have been returned by such an query, False otherwise
	"""
	def doesMatch(entryValue, requestedValue, opcode):
		if isinstance(entryValue, list):
			return any([doesMatch(x, requestedValue, opcode) for x in entryValue])
		if opcode == "=" and entryValue == requestedValue:
			return True
		elif opcode == "<" and entryValue < requestedValue:
			return True
		elif opcode == ">" and entryValue > requestedValue:
			return True
		elif opcode == "<=" and entryValue <= requestedValue:
			return True
		elif opcode == ">=" and entryValue >= requestedValue:
			return True
		return False

	for filterStr, filterValue in singleFilter.items():
		field, opcode = filterStr.split(" ")
		entryValue = entry.get(field)
		if not doesMatch(entryValue, filterValue, opcode):
			return False
	return True


def GetOrInsert(key: Key, **kwargs) -> Entity:
	"""
		Either creates a new entity with the given key, or returns the existing one.

		Its guaranteed that there is no race-condition here; it will never overwrite an
		previously created entity. Extra keyword arguments passed to this function will be
		used to populate the entity if it has to be created; otherwise they are ignored.

		:param key: The key which will be fetched or created.
		:returns: Returns the fetched or newly created Entity.
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


class Query(object):
	"""
		Base Class for querying the datastore. It's API is simmilar to the google.cloud.datastore.query API,
		but it provides the necessary hooks for relational or random queries, the fulltext search as well as support
		for IN filters.
	"""

	def __init__(self, kind: str, srcSkelClass: Union["SkeletonInstance", None] = None, *args, **kwargs):
		"""
			Constructs a new Query.
			:param kind: The kind to run this query on. This may be later overridden to run on a different kind (like
				viur-relations), but it's guaranteed to return only entities of that kind.
			:param srcSkelClass: If set, enables data-model depended queries (like relational queries) as well as the
				:meth:fetch method
		"""
		super(Query, self).__init__()
		self.kind = kind
		self.srcSkel = srcSkelClass
		self.queries: Union[None, QueryDefinition, List[QueryDefinition]] = QueryDefinition(kind, {}, [])
		cbSignature = Union[None, Callable[[Query, str, Union[DATASTORE_BASE_TYPES, List[DATASTORE_BASE_TYPES]]], Union[
			None, Tuple[str, Union[DATASTORE_BASE_TYPES, List[DATASTORE_BASE_TYPES]]]]]]
		self._filterHook: cbSignature = None
		self._orderHook: cbSignature = None
		# Sometimes, the default merge functionality from MultiQuery is not sufficient
		self._customMultiQueryMerge: Union[None, Callable[[Query, List[List[Entity]], int], List[Entity]]] = None
		# Some (Multi-)Queries need a different amount of results per subQuery than actually returned
		self._calculateInternalMultiQueryLimit: Union[None, Callable[[Query, int], int]] = None
		# Allow carrying custom data along with the query. Currently only used by spartialBone to record the guranteed correctnes
		self.customQueryInfo = {}
		self.origKind = kind
		self._lastEntry = None
		self._fulltextQueryString: Union[None, str] = None
		self.lastCursor = None
		if not kind.startswith("viur") and not kwargs.get("_excludeFromAccessLog"):
			currentDbAccessLog.get(set()).add(kind)

	def setFilterHook(self, hook: Callable) -> Optional[Callable]:
		"""
			Installs *hook* as a callback function for new filters.

			*hook* will be called each time a new filter constrain is added to the query.
			This allows e. g. the relationalBone to rewrite constrains added after the initial
			processing of the query has been done (e. g. by ``listFilter()`` methods).

			:param hook: The function to register as callback.
				A value of None removes the currently active hook.
			:returns: The previously registered hook (if any), or None.
		"""
		old = self._filterHook
		self._filterHook = hook
		return old

	def setOrderHook(self, hook: Callable) -> Callable:
		"""
			Installs *hook* as a callback function for new orderings.

			*hook* will be called each time a :func:`db.Query.order` is called on this query.

			:param hook: The function to register as callback.
				A value of None removes the currently active hook.
			:returns: The previously registered hook (if any), or None.
		"""
		old = self._orderHook
		self._orderHook = hook
		return old

	def mergeExternalFilter(self, filters: dict) -> Query:
		return self.mergeFilter(filters)

	def mergeFilter(self, filters: dict) -> Query:
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
			:returns: Returns the query itself for chaining.
		"""
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		if self.queries is None:  # This query is allready unsatifiable and adding more constrains to this wont change this
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
				self.queries = None
		bones = [(y, x) for x, y in skel.items()]
		try:
			# Process filters first
			for bone, key in bones:
				bone.buildDBFilter(key, skel, self, filters)
			# Parse orders
			for bone, key in bones:
				bone.buildDBSort(key, skel, self, filters)
		except RuntimeError as e:
			logging.exception(e)
			self.queries = None
			return self
		if "cursor" in filters and filters["cursor"] and filters["cursor"].lower() != "none":
			self.setCursor(filters["cursor"])
		if "limit" in filters and str(filters["limit"]).isdigit() and int(filters["limit"]) > 0 and int(
			filters["limit"]) <= 100:
			self.limit(int(filters["limit"]))
		return self

	def filter(self, prop: str, value: Union[DATASTORE_BASE_TYPES, List[DATASTORE_BASE_TYPES]]) -> Query:
		"""
			Adds a new constraint to this query.

			The following examples are equivalent: ``filter( "name", "John" )``
			and ``filter( {"name": "John"} )``.

			See also :func:`server.db.Query.mergeFilter` for a safer filter implementation.

			:param prop: Name of the property + operation we'll filter by
			:param value: The value of that filter. Only valid, if *key* is a string.
			:returns: Returns the query itself for chaining.
		"""
		if self.queries is None:
			# This query is already unsatisfiable and adding more constrains to this won't change this
			return self
		if self._filterHook is not None:
			try:
				r = self._filterHook(self, prop, value)
			except RuntimeError:
				self.queries = None
				return self
			if r is None:
				# The Hook did something special directly on 'self' to apply that filter,
				# no need for us to do anything
				return self
			prop, value = r
		if " " not in prop:
			# Ensure that an equality filter is explicitly postfixed with " ="
			field = prop
			op = "="
		else:
			field, op = prop.split(" ")
		if op.lower() in {"!=", "in"}:
			if isinstance(self.queries, list):
				raise NotImplementedError("You cannot use multiple IN or != filter")
			origQuery = self.queries
			self.queries = []
			if op == "!=":
				newFilter = deepcopy(origQuery)
				newFilter.filters["%s <" % field] = value
				self.queries.append(newFilter)
				newFilter = deepcopy(origQuery)
				newFilter.filters["%s >" % field] = value
				self.queries.append(newFilter)
			else:  # IN filter
				if not (isinstance(value, list) or isinstance(value, tuple)):
					raise ValueError("Value must be list or tuple if using IN filter!")
				for val in value:
					newFilter = deepcopy(origQuery)
					newFilter.filters["%s =" % field] = val
					self.queries.append(newFilter)
		else:
			if isinstance(self.queries, list):
				for singeFilter in self.queries:
					singeFilter.filters["%s %s" % (field, op)] = value
			else:  # It must be still a dict (we tested for None already above)
				self.queries.filters["%s %s" % (field, op)] = value
			if op in {"<", "<=", ">", ">="}:
				if isinstance(self.queries, list):
					for queryObj in self.queries:
						if not queryObj.orders or queryObj.orders[0][0] != field:
							queryObj.orders = [(field, SortOrder.Ascending)] + (queryObj.orders or [])
				else:
					if not self.queries.orders or self.queries.orders[0][0] != field:
						self.queries.orders = [(field, SortOrder.Ascending)] + (self.queries.orders or [])
		return self

	def order(self, *orderings: Tuple[str, SortOrder]) -> Query:
		"""
			Specify a query sorting.

			Resulting entities will be sorted by the first property argument, then by the
			second, and so on.

			The following example

			.. code-block:: python

				query = Query( "Person" )
				query.order(("bday" db.SortOrder.Ascending), ("age", db.SortOrder.Descending))

			sorts every Person in order of their birthday, starting with January 1.
			People with the same birthday are sorted by age, oldest to youngest.


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


			:param orderings: The properties to sort by, in sort order.
				Each argument must be a (string, direction) 2-tuple.
			:returns: Returns the query itself for chaining.
		"""
		if self.queries is None:
			# This Query is unsatisfiable - don't try to bother
			return self
		if self._orderHook is not None:
			try:
				orderings = self._orderHook(self, orderings)
			except RuntimeError:
				self.queries = None
				return self
			if orderings is None:
				return self
		if isinstance(self.queries, list):
			for query in self.queries:
				query.orders = list(orderings)
		else:
			self.queries.orders = list(orderings)
		return self

	def setCursor(self, startCursor: str, endCursor: Optional[str] = None) -> Query:
		"""
			Sets the start and optionally end cursor for this query.

			The result set will only include results between these cursors.
			The cursor is generated by an earlier query with exactly the same configuration.

			Its safe to use client-supplied cursors, a cursor can't be abused to access entities
			which don't match the current filters.

			:param startCursor: The start cursor for this query.
			:param endCursor: The end cursor for this query.
			:returns: Returns the query itself for chaining.
		"""
		assert isinstance(self.queries, QueryDefinition)
		self.queries.startCursor = startCursor
		self.queries.endCursor = endCursor
		return self


	def limit(self, limit: int) -> Query:
		"""
			Sets the query limit to *amount* entities in the result.

			Specifying an limit of 0 disables the limit (use with care!).

			:param limit: The maximum number of entities.
			:returns: Returns the query itself for chaining.
		"""
		if isinstance(self.queries, QueryDefinition):
			self.queries.limit = limit
		elif isinstance(self.queries, list):
			for query in self.queries:
				query.limit = limit
		return self

	def distinctOn(self, keyList: List[str]) -> Query:
		"""
			Ensure only entities with distinct values on the fields listed are returned.
			This will implicitly override your SortOrder as all fields listed in keyList have to be sorted first.
		"""
		if isinstance(self.queries, QueryDefinition):
			self.queries.distinct = keyList
		elif isinstance(self.queries, list):
			for query in self.queries:
				query.distinct = keyList
		return self

	def getCursor(self) -> Optional[str]:
		"""
			Get a valid cursor from the last run of this query.

			The source of this cursor varies depending on what the last call was:
			- :func:`server.db.Query.run`: A cursor that points immediately behind the
				last result pulled off the returned iterator.
			- :func:`server.db.Query.get`:: A cursor that points immediately behind the
				last result in the returned list.

			:returns: A cursor that can be used in subsequent query requests or None if that query does not support
				cursors or ther're no more elements to fetch
		"""
		if isinstance(self.queries, QueryDefinition):
			q = self.queries
		elif isinstance(self.queries, list):
			q = self.queries[0]
		return q.currentCursor.decode("ASCII") if q.currentCursor else None

	def getKind(self) -> str:
		"""
			:returns: the *current* kind of this query. This may not be the kind this query has been constructed with
				as relational bones may rewrite this.
		"""
		return self.kind

	def _runSingleFilterQuery(self, query: QueryDefinition, limit: int) -> List[Entity]:
		"""
			Internal helper function that runs a single query definition on the datastore and returns a list of
			entities found.
			:param query: The querydefinition (filters, orders, distinct etc) to run against the datastore
			:param limit: How many results shoult at most be returned
			:return: The first *limit* entities that matches this query
		"""
		qry = __client__.query(kind=query.kind)
		for k, v in query.filters.items():
			key, op = k.split(" ")
			qry.add_filter(key, op, v)
		if query.distinct:
			# Distinct is kinda tricky as all Fieldpaths listed in self._distinct have to be also the first sort orders.
			# We try to keep the requested order intact if possible, otherwise we'll merge / append it to the end
			qry.distinct_on = query.distinct
			newSortOrder = []
			postPonedOrders = {}
			for distinctKey, sortTuple in zip_longest(query.distinct, query.orders):
				if distinctKey and sortTuple:
					(orderProp, orderDir) = sortTuple
					if distinctKey == orderProp:
						newSortOrder.append(sortTuple)
					elif distinctKey in postPonedOrders:
						newSortOrder.append((distinctKey, postPonedOrders[distinctKey]))
						del postPonedOrders[distinctKey]
					else:
						newSortOrder.append((distinctKey, SortOrder.Ascending))
						postPonedOrders[orderProp] = orderDir
				elif distinctKey:
					newSortOrder.append((distinctKey, SortOrder.Ascending))
				elif sortTuple:
					for k, v in postPonedOrders.items():
						newSortOrder.append((k, v))
					postPonedOrders = {}
					newSortOrder.append(sortTuple)
			for k, v in postPonedOrders.items():
				newSortOrder.append((k, v))
			if newSortOrder != query.orders:
				logging.warning("Sortorder fixed to %s due to distinct filtering!" % newSortOrder)
			hasInvertedOrderings = any([x[1] in [SortOrder.InvertedAscending, SortOrder.InvertedDescending]
			                            for x in newSortOrder])
			qry.order = [x[0] if x[1] in [SortOrder.Ascending, SortOrder.InvertedDescending] else "-" + x[0]
			             for x in newSortOrder]
		else:
			hasInvertedOrderings = any([x[1] in [SortOrder.InvertedAscending, SortOrder.InvertedDescending]
			                            for x in query.orders])
			qry.order = [x[0] if x[1] in [SortOrder.Ascending, SortOrder.InvertedDescending] else "-" + x[0]
			             for x in query.orders]
		if dbaccelerator and not IsInTransaction():  # Use the fast-path fetch
			qry.keys_only()
			qryRes = qry.fetch(limit=limit, start_cursor=query.startCursor, end_cursor=query.endCursor)
			res = dbaccelerator.fetchMulti([x.key for x in qryRes])
		else:
			qryRes = qry.fetch(limit=limit, start_cursor=query.startCursor, end_cursor=query.endCursor)
			res = list(qryRes)
		if os.getenv("DATASTORE_EMULATOR_HOST"):
			query.currentCursor = qryRes.next_page_token if query.startCursor != qryRes.next_page_token else None
		else:
			query.currentCursor = qryRes.next_page_token
		res = list(res)
		if hasInvertedOrderings:
			res.reverse()
		return res

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
				key = entry.key
				if key in seenKeys:
					continue
				seenKeys.add(key)
				res.append(entry)
		# Fixme: What about filters that mix different inequality filters - we'll now simply ignore any implicit sortorder
		return self._resortResult(res, {}, self.queries[0].orders)

	def _resortResult(self, entities: List[Entity], filters: Dict[str, DATASTORE_BASE_TYPES],
					  orders: List[Tuple[str, SortOrder]]) -> List[Entity]:
		"""
			Internal helper that takes a (deduplicated) list of entities that has been fetched from different internal
			queries (the datastore does not support IN filters itself, so we have to query each item in that array
			separately) and resorts the list so it matches the query again.

			:param entities: List of entities to resort
			:param filters: The filter used in the query (used to determine implicit sort order by an inequality filter)
			:param orders: The sort-orders to apply
			:return: The sorted list
		"""
		def getVal(src: Entity, fieldVars: Union[str, Tuple[str]], direction: SortOrder) -> Any:
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
			# Lists are handled differently, here the smallest or largest value determines it's position in the result
			if isinstance(src, list) and len(src):
				try:
					src.sort()
				except TypeError:
					# It's a list of dicts or the like for which no useful sort-order is specified
					pass
				if direction == SortOrder.Ascending:
					src = src[0]
				else:
					src = src[-1]
			# We must return this tuple because inter-type comparison isn't possible in Python3 anymore
			return str(type(src)), src if src is not None else 0

		# Check if we have an inequality filter which implies an sortorder
		ineqFilter = None
		for k, _ in filters.items():
			end = k[-2:]
			if "<" in end or ">" in end:
				ineqFilter = k.split(" ")[0]
				break
		if ineqFilter and (not orders or not orders[0][0] == ineqFilter):
			orders = [(ineqFilter, SortOrder.Ascending)] + (orders or [])

		for orderField, direction in orders[::-1]:
			if orderField == KEY_SPECIAL_PROPERTY:
				pass  # FIXME !!
			# entities.sort(key=lambda x: x.key, reverse=direction == SortOrder.Descending)
			else:
				try:
					entities.sort(key=partial(getVal, fieldVars=orderField, direction=direction),
								  reverse=direction == SortOrder.Descending)
				except TypeError:
					# We hit some incomparable types
					pass
		return entities

	def _fixKind(self, resultList: List[Entity]) -> List[Entity]:
		"""
			Jump to parentKind if nessesary (used in realtions)
		"""
		resultList = list(resultList)
		if resultList and resultList[0].key.kind != self.origKind and resultList[0].key.parent and \
			resultList[0].key.parent.kind == self.origKind:
			return list(Get([x.key.parent for x in resultList]))
		return resultList

	def run(self, limit=-1, **kwargs) -> List[Entity]:
		"""
			Run this query.

			It is more efficient to use *limit* if the number of results is known.

			If queried data is wanted as instances of Skeletons, :func:`server.db.Query.fetch`
			should be used.

			:param limit: Limits the query to the defined maximum entities.
			:type limit: int

			:param kwargs: Any keyword arguments accepted by datastore_query.QueryOptions().

			:returns: The list of found entities

			:raises: :exc:`BadFilterError` if a filter string is invalid
			:raises: :exc:`BadValueError` if a filter value is invalid.
			:raises: :exc:`BadQueryError` if an IN filter in combination with a sort order on\
			another property is provided
		"""
		if self.queries is None:
			return None

		if self._fulltextQueryString:
			if IsInTransaction():
				raise InvalidStateError("Can't run fulltextSearch inside transactions!")
			qryStr = self._fulltextQueryString
			self._fulltextQueryString = None  # Reset, so the adapter can still work with this query
			res = self.srcSkel.customDatabaseAdapter.fulltextSearch(qryStr, self)
			if not self.srcSkel.customDatabaseAdapter.fulltextSearchGuaranteesQueryConstrains:
				# Search might yield results that are not included in the listfilter
				if isinstance(self.queries, dict):  # Just one
					res = [x for x in res if _entryMatchesQuery(x, self.queries)]
				else:  # Multi-Query, must match at least one
					res = [x for x in res if any([_entryMatchesQuery(x, y) for y in self.queries])]
		elif isinstance(self.queries, list):
			# We have more than one query to run
			if self._calculateInternalMultiQueryLimit:
				limit = self._calculateInternalMultiQueryLimit(self, limit if limit != -1 else self.queries[0].limit)
			res = []
			# We run all queries first (preventing multiple round-trips to the server)
			for singleQuery in self.queries:
				res.append(self._runSingleFilterQuery(singleQuery, limit if limit != -1 else singleQuery.limit))
			# Wait for the actual results to arrive and convert the protobuffs to Entries
			res = [self._fixKind(x) for x in res]
			if self._customMultiQueryMerge:
				# We have a custom merge function, use that
				res = self._customMultiQueryMerge(self, res, limit if limit != -1 else self.queries[0].limit)
			else:
				# We must merge (and sort) the results ourself
				res = self._mergeMultiQueryResults(res)
		else:  # We have just one single query
			res = self._fixKind(self._runSingleFilterQuery(self.queries, limit if limit != -1 else self.queries.limit))
		if conf["viur.debug.traceQueries"]:
			# orders = self.queries.orders
			filters = self.queries
			distinctOn = ""  # "" distinct on %s" % str(self._distinct) if self._distinct else ""
			if self.kind != self.origKind:
				logging.debug("Queried %s via %s with filter %s and orders %s. Returned %s results" % (
				self.origKind, self.kind, filters, distinctOn, len(res)))
			else:
				logging.debug("Queried %s with filter %s and orders %s. Returned %s results" % (
				self.kind, filters, distinctOn, len(res)))
		if res:
			self._lastEntry = res[-1]
		return res

	def fetch(self, limit: int=-1, **kwargs) -> List[SkeletonInstanceRef]:
		"""
			Run this query and fetch results as :class:`server.skeleton.SkelList`.

			This function is similar to :func:`server.db.Query.run`, but returns a
			:class:`server.skeleton.SkelList` instance instead of Entities.

			:warning: The query must be limited!

			If queried data is wanted as instances of Entity, :func:`server.db.Query.run`
			should be used.

			:param limit: Limits the query to the defined maximum entities.
				A maxiumum value of 99 entries can be fetched at once.

			:raises: :exc:`BadFilterError` if a filter string is invalid
			:raises: :exc:`BadValueError` if a filter value is invalid.
			:raises: :exc:`BadQueryError` if an IN filter in combination with a sort order on
				another property is provided
		"""
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		# limit = limit if limit != -1 else self._limit
		if limit != -1 and not (0 < limit < 100):
			logging.error(("Limit", limit))
			raise NotImplementedError(
				"This query is not limited! You must specify an upper bound using limit() between 1 and 100")
		dbRes = self.run(limit)
		if dbRes is None:
			return None
		res = SkelListRef(self.srcSkel)
		for e in dbRes:
			skelInstance = SkeletonInstanceRef(self.srcSkel.skeletonCls, clonedBoneMap=self.srcSkel.boneMap)
			skelInstance.dbEntity = e
			res.append(skelInstance)
		res.getCursor = lambda: self.getCursor()
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
		if self.queries is None:  # Noting to pull here
			raise StopIteration()
		elif isinstance(self.queries, list):
			raise ValueError("No iter on Multiqueries")
		while True:
			qryRes = self._runSingleFilterQuery(self.queries, 20)
			yield from qryRes
			if not self.queries.currentCursor:  # We reached the end of that query
				break
			self.queries.startCursor = self.queries.currentCursor

	def getEntry(self) -> Union[None, Entity]:
		"""
			Returns only the first entity of the current query.

			:returns: The first entity on success, or None if the result-set is empty.
		"""
		try:
			res = list(self.run(limit=1))[0]
			return res
		except (IndexError, TypeError):  # Empty result-set
			return None

	def getSkel(self) -> Optional[SkeletonInstanceRef]:
		"""
			Returns a matching :class:`server.db.skeleton.Skeleton` instance for the
			current query.

			Its only possible to use this function if this query has been created using
			:func:`server.skeleton.Skeleton.all`.

			:returns: The Skeleton or None if the result-set is empty.
		"""
		if self.srcSkel is None:
			raise NotImplementedError("This query has not been created using skel.all()")
		res = self.getEntry()
		if res is None:
			return None
		self.srcSkel.setEntity(res)
		return self.srcSkel

	def clone(self, keysOnly=None) -> Query:
		"""
			Returns a deep copy of the current query.

			:param keysOnly: If the query should be used to retrieve entity keys only\
			in the new query.
			:type keysOnly: bool

			:returns: The cloned query.
			:rtype: server.db.Query
		"""
		res = Query(self.getKind(), self.srcSkel)
		res.kind = self.kind
		res.queries = deepcopy(self.queries)
		# res.filters = deepcopy(self.filters)
		# res.orders = deepcopy(self.orders)
		# res._limit = self._limit
		res._filterHook = self._filterHook
		res._orderHook = self._orderHook
		# res._startCursor = self._startCursor
		# res._endCursor = self._endCursor
		res._customMultiQueryMerge = self._customMultiQueryMerge
		res._calculateInternalMultiQueryLimit = self._calculateInternalMultiQueryLimit
		res.customQueryInfo = self.customQueryInfo
		res.origKind = self.origKind
		res._fulltextQueryString = self._fulltextQueryString
		# res._distinct = self._distinct
		return res

	def __repr__(self):
		return "<db.Query on %s with queries %s>" % (self.kind, self.queries)


def IsInTransaction() -> bool:
	return __client__.current_transaction is not None


def acquireTransactionSuccessMarker() -> str:
	"""
		Generates a token that will be written to the firestore (under "viur-transactionmarker") if the transaction
		completes successfully. Currently only used by deferredTasks to check if the task should actually execute
		or if the transaction it was created in failed.
		:return: Name of the entry in viur-transactionmarker
	"""
	txn = __client__.current_transaction
	assert txn, "acquireTransactionSuccessMarker cannot be called outside an transaction"
	marker = binascii.b2a_hex(txn.id).decode("ASCII")
	if not "viurTxnMarkerSet" in dir(txn):
		e = Entity(Key("viur-transactionmarker", marker))
		e["creationdate"] = datetime.now()
		Put(e)
		txn.viurTxnMarkerSet = True
	return marker


def RunInTransaction(callee: Callable, *args, **kwargs) -> Any:
	"""
		Runs the function given in :param:callee inside a transaction.
		Inside a transaction it's guaranteed that
		- either all or no changes are written to the datastore
		- no other transaction is currently reading/writing the entities accessed

		See (transactions)[https://cloud.google.com/datastore/docs/concepts/cloud-datastore-transactions] for more
		information.

		..Warning: The datastore may produce unexpected results if a entity that have been written inside a transaction
			is read (or returned in a query) again. In this case you will the the *old* state of that entity. Keep that
			in mind if wrapping functions to run in a transaction that may have not been designed to handle this case.
		:param callee: The function that will be run inside a transaction
		:param args: All args will be passed into the callee
		:param kwargs: All kwargs will be passed into the callee
		:return: Whatever the callee function returned
	"""
	with __client__.transaction():
		res = callee(*args, **kwargs)
	return res


__all__ = [KEY_SPECIAL_PROPERTY, DATASTORE_BASE_TYPES, SortOrder, Entity, Key, KeyClass, Put, Get, Delete, AllocateIds,
		   Conflict, Error, keyHelper, fixUnindexableProperties, GetOrInsert, Query, IsInTransaction,
		   acquireTransactionSuccessMarker, RunInTransaction]
