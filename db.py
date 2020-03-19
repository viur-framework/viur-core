# -*- coding: utf-8 -*-
from __future__ import annotations
from viur.core.config import conf
from viur.core import utils
import logging
from typing import Union, Tuple, List, Dict, Any, Callable
from functools import partial
from copy import deepcopy
from google.cloud import datastore, exceptions
from enum import Enum
from datetime import datetime, date, time
import binascii
import contextlib
from time import time as ttime

"""
	Tiny wrapper around *google.appengine.api.datastore*.

	This just ensures that operations issued directly through the database-api
	doesn't interfere with ViURs internal caching. If you need skeletons anyway,
	query the database using skel.all(); its faster and is able to serve more
	requests from cache.
"""

__client__ = datastore.Client()

# Consts
KEY_SPECIAL_PROPERTY = "__key__"
DATASTORE_BASE_TYPES = Union[None, str, int, float, bool, datetime, date, time, datastore.Key]


class SortOrder(Enum):
	Ascending = 1
	Descending = 2
	InvertedAscending = 3
	InvertedDescending = 4


# Proxied Function / Classed
Entity = datastore.Entity
Key = __client__.key  # Proxy-Function
KeyClass = datastore.Key  # Expose the class also
Get = __client__.get
#Delete = __client__.delete
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


def Put(entity: Union[Entity, List[Entity]]):
	"""
		Save an entity in the Cloud Datastore.
		Also ensures that no string-key with an digit-only name can be used.
		:param entity: The entity to be saved to the datastore.
	"""
	if not isinstance(entity, list):
		entity = [entity]
	for e in entity:
		if not e.key.is_partial and e.key.name and e.key.name.isdigit():
			raise ValueError("Cannot store an entity with digit-only string key")
		fixUnindexableProperties(e)
	return __client__.put_multi(entities=entity)


def Delete(keys: Union[Entity, List[Entity], KeyClass, List[KeyClass]]):
	if isinstance(keys, list):
		return __client__.delete_multi([(x if isinstance(x, KeyClass) else x.key) for x in keys ])
	else:
		if isinstance(keys, KeyClass):
			return __client__.delete(keys)
		else:
			return __client__.delete(keys.key)


def fixUnindexableProperties(entry: Entity):
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
			else:
				resList.append(k)
	entry.exclude_from_indexes = resList
	return entry


def _entryMatchesQuery(entry: Entity, singleFilter: dict) -> bool:
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


class Query(object):
	"""
		Base Class for querying the firestore
	"""

	# Fixme: Typing for Skeleton-Class we can't import here?
	def __init__(self, collection: str, srcSkelClass: Union[None, Any] = None, *args, **kwargs):
		super(Query, self).__init__()
		self.collection = collection
		self.srcSkel = srcSkelClass
		self.filters: Union[None, Dict[str: DATASTORE_BASE_TYPES], List[Dict[str: DATASTORE_BASE_TYPES]]] = {}
		self.orders: List[Tuple[str, SortOrder]] = [(KEY_SPECIAL_PROPERTY, SortOrder.Ascending)]
		self.amount: int = 30
		cbSignature = Union[None, Callable[[Query, str, Union[DATASTORE_BASE_TYPES, List[DATASTORE_BASE_TYPES]]], Union[
			None, Tuple[str, Union[DATASTORE_BASE_TYPES, List[DATASTORE_BASE_TYPES]]]]]]
		self._filterHook: cbSignature = None
		self._orderHook: cbSignature = None
		self._startCursor = None
		self._endCursor = None
		# Sometimes, the default merge functionality from MultiQuery is not sufficient
		self._customMultiQueryMerge: Union[None, Callable[[Query, List[List[Entity]], int], List[Entity]]] = None
		# Some (Multi-)Queries need a different amount of results per subQuery than actually returned
		self._calculateInternalMultiQueryAmount: Union[None, Callable[[Query, int], int]] = None
		# Allow carrying custom data along with the query. Currently only used by spartialBone to record the guranteed correctnes
		self.customQueryInfo = {}
		self.origCollection = collection
		self._lastEntry = None
		self._fulltextQueryString: Union[None, str] = None
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
		return old

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
		return old

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
			# Process filters first
			for bone, key in bones:
				bone.buildDBFilter(key, skel, self, filters)
			# Parse orders
			for bone, key in bones:
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
		return self

	def filter(self, prop: str, value: Union[DATASTORE_BASE_TYPES, List[DATASTORE_BASE_TYPES]]) -> Query:
		"""
			Adds a new constraint to this query.

			The following examples are equivalent: ``filter( "name", "John" )``
			and ``filter( {"name": "John"} )``.

			See also :func:`server.db.Query.mergeExternalFilter` for a safer filter implementation.

			:param prop: Name of the property + operation we'll filter by

			:param value: The value of that filter. Only valid, if *key* is a string.

			:returns: Returns the query itself for chaining.
			:rtype: server.db.Query
		"""
		if self.filters is None:
			# This query is already unsatisfiable and adding more constrains to this won't change this
			return self
		if self._filterHook is not None:
			try:
				r = self._filterHook(self, prop, value)
			except RuntimeError:
				self.filters = None
				return self
			if r is None:
				# The Hook did something special directly on 'self' to apply that filter,
				# no need for us to do anything
				return self
			filter, value = r
		if " " not in prop:
			# Ensure that an equality filter is explicitly postfixed with " ="
			field = prop
			op = "="
		else:
			field, op = prop.split(" ")
		if op.lower() in {"!=", "in"}:
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
					raise ValueError("Value must be list or tuple if using IN filter!")
				for val in value:
					newFilter = {k: v for k, v in origFilter.items()}
					newFilter["%s =" % field] = val
					self.filters.append(newFilter)
		else:
			if isinstance(self.filters, list):
				for singeFilter in self.filters:
					singeFilter["%s %s" % (field, op)] = value
			else:  # It must be still a dict (we tested for None already above)
				self.filters["%s %s" % (field, op)] = value
			if op in {"<", "<=", ">", ">="} and (len(self.orders) == 0 or self.orders[0][0] != field):
				self.order((field, SortOrder.Ascending), *self.orders)
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


			:param orderings: The properties to sort by, in sort order.\
			Each argument must be a (string, direction) 2-tuple.

			:returns: Returns the query itself for chaining.
		"""
		if self.filters is None:
			# This Query is unsatisfiable - don't try to bother
			return self
		if self._orderHook is not None:
			try:
				orderings = self._orderHook(self, orderings)
			except RuntimeError:
				self.datastoreQuery = None
				return self
			if orderings is None:
				return self
		self.orders = orderings
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
		return self.datastoreQuery.IsKeysOnly()

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

	def _runSingleFilterQuery(self, filters, amount):
		qry = __client__.query(kind=self.getKind())
		for k, v in filters.items():
			key, op = k.split(" ")
			qry.add_filter(key, op, v)
		qry.order = [x[0] if x[1] == SortOrder.Ascending else "-" + x[0] for x in self.orders]
		qryRes = qry.fetch(limit=amount, start_cursor=self._startCursor, end_cursor=self._endCursor)
		res = next(qryRes.pages)
		self.lastCursor = qryRes.next_page_token
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
		return self._resortResult(res, {}, self.orders)

	def _resortResult(self, entities: List[Entity], filters: Dict[str, DATASTORE_BASE_TYPES],
					  orders: List[Tuple[str, SortOrder]]) -> List[Entity]:

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
			if IsInTransaction():
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
				qryLimit = self._calculateInternalMultiQueryAmount(self, qryLimit)
			res = []
			# We run all queries first (preventing multiple round-trips to the server)
			for singleFilter in self.filters:
				res.append(self._runSingleFilterQuery(
					filters=singleFilter,
					amount=qryLimit))
			# Wait for the actual results to arrive and convert the protobuffs to Entries
			res = [list(x) for x in res]
			if self._customMultiQueryMerge:
				# We have a custom merge function, use that
				res = self._customMultiQueryMerge(self, res, origLimit)
			else:
				# We must merge (and sort) the results ourself
				res = self._mergeMultiQueryResults(res)
		else:  # We have just one single query
			res = list(self._runSingleFilterQuery(self.filters, qryLimit))
		if conf["viur.debug.traceQueries"]:
			kindName = self.origCollection
			orders = self.orders
			filters = self.filters
			logging.debug(
				"Queried %s with filter %s and orders %s. Returned %s results" % (kindName, filters, orders, len(res)))
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
		dbRes = self.run(amount)
		if dbRes is None:
			return None
		res = SkelListRef(self.srcSkel)
		for e in dbRes:
			skelInstance = SkeletonInstanceRef(self.srcSkel.skeletonCls, clonedBoneMap=self.srcSkel.boneMap)
			skelInstance.dbEntity = e
			res.append(skelInstance)
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
		if self.filters is None:  # Noting to pull here
			raise StopIteration()
		elif isinstance(self.filters, list):
			raise ValueError("No iter on Multiqueries")
		while True:
			qryRes = self._runSingleFilterQuery(self.filters, 20)
			yield from qryRes
			if not self.lastCursor:  # We reached the end of that query
				break
			self._startCursor = self.lastCursor

	def get(self) -> Union[None, Entity]:
		"""
			Returns only the first entity of the current query.

			:returns: dict on success, or None if the result-set is empty.
			:rtype: dict
		"""
		try:
			res = list(self.run(limit=1))[0]
			return res
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
			return None
		self.srcSkel.setEntity(res)
		return self.srcSkel

	def clone(self, keysOnly=None):
		"""
			Returns a deep copy of the current query.

			:param keysOnly: If the query should be used to retrieve entity keys only\
			in the new query.
			:type keysOnly: bool

			:returns: The cloned query.
			:rtype: server.db.Query
		"""
		raise NotImplemented  # For now...
		# FIXME: Is everything covered?
		res = Query(self.getKind(), self.srcSkel)
		res.limit(self.amount)
		res.filters = deepcopy(self.filters)
		res.orders = deepcopy(self.orders)
		res._fulltextQueryString = self._fulltextQueryString
		return res

	def __repr__(self):
		return "<db.Query on %s with filters %s and orders %s>" % (self.collection, self.filters, self.orders)


def IsInTransaction():
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
	marker = binascii.b2a_hex(txn.id)
	if not "viurTxnMarkerSet" in dir(txn):
		e = Entity(Key("viur-transactionmarker", marker))
		e["creationdate"] = datetime.now()
		Put(e)
		txn.viurTxnMarkerSet = True
	return marker


def RunInTransaction(callee, *args, **kwargs):
	with __client__.transaction():
		res = callee(*args, **kwargs)
	return res


__all__ = [KEY_SPECIAL_PROPERTY, DATASTORE_BASE_TYPES, SortOrder, Entity, Key, KeyClass, Put, Get, Delete, AllocateIds,
		   Conflict, Error, keyHelper, fixUnindexableProperties, GetOrInsert, Query, IsInTransaction,
		   acquireTransactionSuccessMarker, RunInTransaction]
