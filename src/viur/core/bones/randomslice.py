from random import random, sample, shuffle
import typing as t

from itertools import chain
from math import ceil

from viur.core import db
from viur.core.bones.base import BaseBone


class RandomSliceBone(BaseBone):
    """
    This class is particularly useful when you want to retrieve a random sample of elements from a
    larger dataset without needing to fetch all the data from the database. By performing multiple
    subqueries and processing the results, RandomSliceBone provides an efficient way to get a
    randomized selection of elements from the database query.
    Simulates the orderby=random from SQL.
    If you sort by this bone, the query will return a random set of elements from that query.

    :param visible: Indicates if the bone is visible, defaults to False.
    :param readOnly: Indicates if the bone is read-only, defaults to True.
    :param slices: The number of slices to use, defaults to 2.
    :param sliceSize: The size of each slice, defaults to 0.5.
    :param kwargs: Additional keyword arguments.
    """

    type = "randomslice"

    def __init__(self, *, visible=False, readOnly=True, slices=2, sliceSize=0.5, **kwargs):
        """
            Initializes a new RandomSliceBone.


        """
        if visible or not readOnly:
            raise NotImplemented("A RandomSliceBone must not visible and readonly!")
        super().__init__(indexed=True, visible=False, readOnly=True, **kwargs)
        self.slices = slices
        self.sliceSize = sliceSize

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        """
        Serializes the bone into a format that can be written into the datastore. Instead of using
        the existing value, it writes a randomly chosen float in the range [0, 1) as the value for
        this bone.

        :param SkeletonInstance skel: The SkeletonInstance this bone is part of.
        :param str name: The property name this bone has in its Skeleton (not the description).
        :param bool parentIndexed: Indicates if the parent bone is indexed.
        :return: Returns True if the serialization is successful.
        :rtype: bool
        """
        skel.dbEntity[name] = random()
        skel.dbEntity.exclude_from_indexes.discard(name)  # Random bones can never be not indexed
        return True

    def buildDBSort(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: dict
    ) -> t.Optional[db.Query]:
        """
        Modifies the database query to return a random selection of elements by creating multiple
        subqueries, each covering a slice of the data. This method doesn't just change the order of
        the selected elements, but also changes which elements are returned.

        :param str name: The property name this bone has in its Skeleton (not the description).
        :param SkeletonInstance skel: The :class:viur.core.skeleton.Skeleton instance this bone is part of.
        :param db.Query dbFilter: The current :class:viur.core.db.Query instance the filters should be applied to.
        :param Dict rawFilter: The dictionary of filters the client wants to have applied.
        :return: The modified :class:viur.core.db.Query instance.
        :rtype: Optional[db.Query]

        .. note:: The rawFilter is controlled by the client, so you must expect and safely handle
            malformed data.

        The method also contains an inner function, applyFilterHook, that applies the filter hook to
        the given filter if set, or returns the unmodified filter. This allows the orderby=random
        functionality to be used in relational queries as well.
        """

        def applyFilterHook(dbfilter, property, value):
            """
                Applies dbfilter._filterHook to the given filter if set,
                else return the unmodified filter.
                Allows orderby=random also be used in relational-queries.
            """
            if dbFilter._filterHook is None:
                return property, value
            try:
                property, value = dbFilter._filterHook(dbFilter, property, value)
            except:
                # Either, the filterHook tried to do something special to dbFilter (which won't
                # work as we are currently rewriting the core part of it) or it thinks that the query
                # is unsatisfiable (fe. because of a missing ref/parent key in RelationalBone).
                # In each case we kill the query here - making it to return no results
                raise RuntimeError()
            return property, value

        if "orderby" in rawFilter and rawFilter["orderby"] == name:
            # We select a random set of elements from that collection
            assert not isinstance(dbFilter.queries,
                                  list), "Orderby random is not possible on a query that already uses an IN-filter!"
            origFilter: dict = dbFilter.queries.filters
            origKind = dbFilter.getKind()
            queries = []
            for unused in range(0, self.slices):  # Fetch 3 Slices from the set
                rndVal = random()  # Choose our Slice center
                # Right Side
                q = db.QueryDefinition(origKind, {}, [])
                property, value = applyFilterHook(dbFilter, f"{name} <=", rndVal)
                q.filters[property] = value
                q.orders = [(name, db.SortOrder.Descending)]
                queries.append(q)
                # Left Side
                q = db.QueryDefinition(origKind, {}, [])
                property, value = applyFilterHook(dbFilter, f"{name} >", rndVal)
                q.filters[property] = value
                q.orders = [(name, db.SortOrder.Ascending)]
                queries.append(q)
            dbFilter.queries = queries
            # Map the original filter back in
            for k, v in origFilter.items():
                dbFilter.filter(k, v)
            dbFilter._customMultiQueryMerge = self.customMultiQueryMerge
            dbFilter._calculateInternalMultiQueryLimit = self.calculateInternalMultiQueryLimit

    def calculateInternalMultiQueryLimit(self, query: db.Query, targetAmount: int) -> int:
        """
        Calculates the number of entries to be fetched in each subquery.

        :param db.Query query: The :class:viur.core.db.Query instance.
        :param int targetAmount: The number of entries to be returned from the db.Query.
        :return: The number of elements the db.Query should fetch on each subquery.
        :rtype: int
        """
        return ceil(targetAmount * self.sliceSize)

    def customMultiQueryMerge(self, dbFilter: db.Query, result: list[db.Entity], targetAmount: int) \
            -> list[db.Entity]:
        """
        Merges the results of multiple subqueries by randomly selecting 'targetAmount' elements
        from the combined 'result' list.

        :param db.Query dbFilter: The db.Query instance calling this function.
        :param List[db.Entity] result: The list of results for each subquery that has been run.
        :param int targetAmount: The number of results to be returned from the db.Query.
        :return: A list of elements to be returned from the db.Query.
        :rtype: List[db.Entity]
        """
        # res is a list of iterators at this point, chain them together
        res = chain(*[list(x) for x in result])
        # Remove duplicates
        tmpDict = {}
        for item in res:
            tmpDict[str(item.key)] = item
        res = list(tmpDict.values())
        # Slice the requested amount of results our 3times lager set
        res = sample(res, min(len(res), targetAmount))
        shuffle(res)
        return res
