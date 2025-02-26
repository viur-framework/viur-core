from __future__ import annotations

import base64
import copy
import functools
import logging
import typing as t
from .config import conf
from .transport import Count, Get, runSingleFilter
from .types import (
    currentDbAccessLog,
    DATASTORE_BASE_TYPES,
    Entity,
    KEY_SPECIAL_PROPERTY,
    QueryDefinition,
    SkelListRef,
    SortOrder,
)
from .utils import IsInTransaction

if t.TYPE_CHECKING:
    from viur.core.skeleton import SkeletonInstance


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


class Query(object):
    """
        Base Class for querying the datastore. It's API is similar to the google.cloud.datastore.query API,
        but it provides the necessary hooks for relational or random queries, the fulltext search as well as support
        for IN filters.
    """

    def __init__(self, kind: str, srcSkelClass: t.Union["SkeletonInstance", None] = None, *args, **kwargs):
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
        self.queries: t.Union[None, QueryDefinition, t.List[QueryDefinition]] = QueryDefinition(kind, {}, [])
        cbSignature = t.Union[None, t.Callable[[Query, str, t.Union[DATASTORE_BASE_TYPES, t.List[DATASTORE_BASE_TYPES]]], t.Union[
            None, t.Tuple[str, t.Union[DATASTORE_BASE_TYPES, t.List[DATASTORE_BASE_TYPES]]]]]]
        self._filterHook: cbSignature = None
        self._orderHook: cbSignature = None
        # Sometimes, the default merge functionality from MultiQuery is not sufficient
        self._customMultiQueryMerge: t.Union[None, t.Callable[[Query, t.List[t.List[Entity]], int], t.List[Entity]]] = None
        # Some (Multi-)Queries need a different amount of results per subQuery than actually returned
        self._calculateInternalMultiQueryLimit: t.Union[None, t.Callable[[Query, int], int]] = None
        # Allow carrying custom data along with the query. Currently only used by spartialBone to record the guranteed correctnes
        self.customQueryInfo = {}
        self.origKind = kind
        self._lastEntry = None
        self._fulltextQueryString: t.Union[None, str] = None
        self.lastCursor = None
        # if not kind.startswith("viur") and not kwargs.get("_excludeFromAccessLog"):
        #     accessLog = currentDbAccessLog.get()
        #     if isinstance(accessLog, set):
        #         accessLog.add(kind)

    def setFilterHook(self, hook: t.Callable) -> t.Optional[t.Callable]:
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

    def setOrderHook(self, hook: t.Callable) -> t.Callable:
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

    def mergeExternalFilter(self, filters: dict) -> 'Query':
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
        startCursor = endCursor = None
        if "cursor" in filters and filters["cursor"] and filters["cursor"].lower() != "none":
            startCursor = filters["cursor"]
        if "endcursor" in filters and filters["endcursor"] and filters["endcursor"].lower() != "none":
            endCursor = filters["endcursor"]
        if startCursor or endCursor:
            self.setCursor(startCursor, endCursor)
        if "limit" in filters and str(filters["limit"]).isdigit() and int(filters["limit"]) > 0 and int(
            filters["limit"]) <= 100:
            self.limit(int(filters["limit"]))
        return self

    def filter(self, prop: str, value: t.Union[DATASTORE_BASE_TYPES, t.List[DATASTORE_BASE_TYPES]]) -> 'Query':
        """
            Adds a new constraint to this query.

            The following examples are equivalent: ``filter( "name", "John" )``
            and ``filter( {"name": "John"} )``.

            See also :func:`server.db.Query.mergeExternalFilter` for a safer filter implementation.

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
                newFilter = copy.deepcopy(origQuery)
                newFilter.filters["%s <" % field] = value
                self.queries.append(newFilter)
                newFilter = copy.deepcopy(origQuery)
                newFilter.filters["%s >" % field] = value
                self.queries.append(newFilter)
            else:  # IN filter
                if not (isinstance(value, list) or isinstance(value, tuple)):
                    raise ValueError("Value must be list or tuple if using IN filter!")
                for val in value:
                    newFilter = copy.deepcopy(origQuery)
                    newFilter.filters["%s =" % field] = val
                    self.queries.append(newFilter)
        else:
            filterStr = "%s %s" % (field, op)
            if isinstance(self.queries, list):
                for singeFilter in self.queries:
                    if filterStr not in singeFilter.filters:
                        singeFilter.filters[filterStr] = value
                    else:
                        if not isinstance(singeFilter.filters[filterStr]):
                            singeFilter.filters[filterStr] = [singeFilter.filters[filterStr]]
                        singeFilter.filters[filterStr].append(value)
            else:  # It must be still a dict (we tested for None already above)
                if filterStr not in self.queries.filters:
                    self.queries.filters[filterStr] = value
                else:
                    if not isinstance(self.queries.filters[filterStr], list):
                        self.queries.filters[filterStr] = [self.queries.filters[filterStr]]
                    self.queries.filters[filterStr].append(value)
            if op in {"<", "<=", ">", ">="}:
                if isinstance(self.queries, list):
                    for queryObj in self.queries:
                        if not queryObj.orders or queryObj.orders[0][0] != field:
                            queryObj.orders = [(field, SortOrder.Ascending)] + (queryObj.orders or [])
                else:
                    if not self.queries.orders or self.queries.orders[0][0] != field:
                        self.queries.orders = [(field, SortOrder.Ascending)] + (self.queries.orders or [])
        return self

    def order(self, *orderings: t.Tuple[str, 'SortOrder']) -> 'Query':
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
            passed to ``order()``. t.Any number of sort orders may be used after the
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

        # Check for correct order subscript
        orders = []
        for order in orderings:
            if isinstance(order, str):
                order = (order, SortOrder.Ascending)

            if not (isinstance(order[0], str) and isinstance(order[1], SortOrder)):
                raise TypeError(
                    f"Invalid ordering {order}, it has to be a tuple. Try: `(\"{order}\", SortOrder.Ascending)`")

            orders.append(order)

        orderings = tuple(orders)

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

    def setCursor(self, startCursor: str, endCursor: t.Optional[str] = None) -> 'Query':
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
        if isinstance(self.queries, list):
            for query in self.queries:
                assert isinstance(query, QueryDefinition)
                if startCursor:
                    query.startCursor = base64.urlsafe_b64decode(startCursor.encode("ASCII")).decode("ASCII")
                if endCursor:
                    query.endCursor = base64.urlsafe_b64decode(endCursor.encode("ASCII")).decode("ASCII")
        else:
            assert isinstance(self.queries, QueryDefinition)
            if startCursor:
                self.queries.startCursor = base64.urlsafe_b64decode(startCursor.encode("ASCII")).decode("ASCII")
            if endCursor:
                self.queries.endCursor = base64.urlsafe_b64decode(endCursor.encode("ASCII")).decode("ASCII")
        return self

    def limit(self, limit: int) -> 'Query':
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

    def distinctOn(self, keyList: t.List[str]) -> 'Query':
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

    def getCursor(self) -> t.Optional[str]:
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
        return base64.urlsafe_b64encode(q.currentCursor).decode("ASCII") if q.currentCursor else None

    def get_orders(self) -> t.List[t.Tuple[str, SortOrder]] | None:
        """
            Get the orders from this query.

            :returns: The orders form this query as a list if there is no orders set it returns None
        """
        q = self.queries

        if isinstance(q, (list, tuple)):
            q = q[0]

        if not isinstance(q, QueryDefinition):
            raise ValueError(
                f"self.queries can only be a 'QueryDefinition' or a list of, but found {self.queries!r}"
            )

        return q.orders or None

    def getKind(self) -> str:
        """
            :returns: the *current* kind of this query. This may not be the kind this query has been constructed with
                as relational bones may rewrite this.
        """
        return self.kind

    def _runSingleFilterQuery(self, query: QueryDefinition, limit: int) -> t.List[Entity]:
        """
            Internal helper function that runs a single query definition on the datastore and returns a list of
            entities found.
            :param query: The querydefinition (filters, orders, distinct etc) to run against the datastore
            :param limit: How many results shoult at most be returned
            :return: The first *limit* entities that matches this query
        """
        return runSingleFilter(query, limit)

    def _mergeMultiQueryResults(self, inputRes: t.List[t.List[Entity]]) -> t.List[Entity]:
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

    def _resortResult(self, entities: t.List[Entity], filters: t.Dict[str, DATASTORE_BASE_TYPES],
                      orders: t.List[t.Tuple[str, 'SortOrder']]) -> t.List[Entity]:
        """
            Internal helper that takes a (deduplicated) list of entities that has been fetched from different internal
            queries (the datastore does not support IN filters itself, so we have to query each item in that array
            separately) and resorts the list so it matches the query again.

            :param entities: t.List of entities to resort
            :param filters: The filter used in the query (used to determine implicit sort order by an inequality filter)
            :param orders: The sort-orders to apply
            :return: The sorted list
        """

        def getVal(src: Entity, fieldVars: t.Union[str, t.Tuple[str]], direction: SortOrder) -> t.Any:
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
                    entities.sort(key=functools.partial(getVal, fieldVars=orderField, direction=direction),
                                  reverse=direction == SortOrder.Descending)
                except TypeError:
                    # We hit some incomparable types
                    pass
        return entities

    def _fixKind(self, resultList: t.List[Entity]) -> t.List[Entity]:
        """
            Jump to parentKind if necessary (used in relations)
        """
        resultList = list(resultList)
        if resultList and resultList[0].key.kind != self.origKind and resultList[0].key.parent and \
            resultList[0].key.parent.kind == self.origKind:
            return list(Get(list(dict.fromkeys([x.key.parent for x in resultList]))))
        return resultList

    def run(self, limit: int = -1) -> t.List[Entity]:
        """
            Run this query.

            It is more efficient to use *limit* if the number of results is known.

            If queried data is wanted as instances of Skeletons, :func:`server.db.Query.fetch`
            should be used.

            :param limit: Limits the query to the defined maximum entities.

            :returns: The list of found entities

            :raises: :exc:`BadFilterError` if a filter string is invalid
            :raises: :exc:`BadValueError` if a filter value is invalid.
            :raises: :exc:`BadQueryError` if an IN filter in combination with a sort order on\
            another property is provided
        """
        if self.queries is None:
            if conf["traceQueries"]:
                logging.debug("Query on %s aborted as being not satisfiable" % self.kind)
            return []

        if self._fulltextQueryString:
            if IsInTransaction():
                raise ValueError("Can't run fulltextSearch inside transactions!")  # InvalidStateError FIXME!
            qryStr = self._fulltextQueryString
            self._fulltextQueryString = None  # Reset, so the adapter can still work with this query
            res = self.srcSkel.customDatabaseAdapter.fulltextSearch(qryStr, self)
            if not self.srcSkel.customDatabaseAdapter.fulltextSearchGuaranteesQueryConstrains:
                # Search might yield results that are not included in the listfilter
                if isinstance(self.queries, QueryDefinition):  # Just one
                    res = [x for x in res if _entryMatchesQuery(x, self.queries.filters)]
                else:  # Multi-Query, must match at least one
                    res = [x for x in res if any([_entryMatchesQuery(x, y.filters) for y in self.queries])]
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
        if res:
            self._lastEntry = res[-1]
        return res

    def count(self, up_to: int = 2 ** 63 - 1) -> int:
        """
            The count operation cost one entity read for up to 1,000 index entries matched
            (https://cloud.google.com/datastore/docs/aggregation-queries#pricing)
            :param up_to can be sigend int 64 bit (max positive 2^31-1)

            :returns: Count entries for this query.
        """
        if self.queries is None:
            if conf["traceQueries"]:
                logging.debug("Query on %s aborted as being not satisfiable" % self.kind)
            return -1
        elif isinstance(self.queries, list):
            raise ValueError("No count on Multiqueries")
        else:
            return Count(queryDefinition=self.queries, up_to=up_to)

    def fetch(self, limit: int = -1) -> SkelListRef['SkeletonInstance'] | None:
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
        assert conf["SkeletonInstanceRef"] is not None, "conf['SkeletonInstanceRef'] has not been set!"
        if self.srcSkel is None:
            raise NotImplementedError("This query has not been created using skel.all()")
        # limit = limit if limit != -1 else self._limit
        if limit != -1 and not (0 < limit <= 100):
            logging.error(("Limit", limit))
            raise NotImplementedError(
                "This query is not limited! You must specify an upper bound using limit() between 1 and 100")
        dbRes = self.run(limit)
        if dbRes is None:
            return None
        res = SkelListRef(self.srcSkel)
        for e in dbRes:
            skelInstance = conf["SkeletonInstanceRef"](self.srcSkel.skeletonCls, clonedBoneMap=self.srcSkel.boneMap)
            skelInstance.dbEntity = e
            res.append(skelInstance)
        res.getCursor = lambda: self.getCursor()
        res.get_orders = lambda: self.get_orders()
        return res

    def iter(self) -> t.Iterator[Entity]:
        """
            Run this query and return an iterator for the results.

            The advantage of this function is, that it allows for iterating
            over a large result-set, as it hasn't have to be pulled in advance
            from the data store.

            This function intentionally ignores a limit set by :func:`server.db.Query.limit`.

            :warning: If iterating over a large result set, make sure the query supports cursors. \
            Otherwise, it might not return all results as the AppEngine doesn't maintain the view \
            for a query for more than ~30 seconds.
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

    def getEntry(self) -> t.Union[None, Entity]:
        """
            Returns only the first entity of the current query.

            :returns: The first entity on success, or None if the result-set is empty.
        """
        try:
            res = list(self.run(limit=1))[0]
            return res
        except (IndexError, TypeError):  # Empty result-set
            return None

    def getSkel(self) -> t.Optional['SkeletonInstance']:
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

    def clone(self) -> 'Query':
        """
            Returns a deep copy of the current query.

            :returns: The cloned query.
        """
        res = Query(self.getKind(), self.srcSkel)
        res.kind = self.kind
        res.queries = copy.deepcopy(self.queries)
        # res.filters = copy.deepcopy(self.filters)
        # res.orders = copy.deepcopy(self.orders)
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
