from viur.core.bones.base import BaseBone
from viur.core import db
from typing import Dict, List, Optional
from random import random, sample, shuffle
from itertools import chain
from math import ceil


class RandomSliceBone(BaseBone):
    """
        Simulates the orderby=random from SQL.
        If you sort by this bone, the query will return a random set of elements from that query.
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
            Serializes this bone into something we
            can write into the datastore.

            This time, we just ignore whatever is set on this bone and write a randomly chosen
            float [0..1) as value for this bone.

            :param name: The property-name this bone has in its Skeleton (not the description!)
        """
        skel.dbEntity[name] = random()
        skel.dbEntity.exclude_from_indexes.discard(name)  # Random bones can never be not indexed
        return True

    def buildDBSort(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: Dict
    ) -> Optional[db.Query]:
        """
            Same as buildDBFilter, but this time its not about filtering
            the results, but by sorting them.
            Again: rawFilter is controlled by the client, so you *must* expect and safely handle
            malformed data!

            This function is somewhat special as it doesn't just change in which order the selected
            Elements are being returned - but also changes *which* Elements are beeing returned (=>
            a random selection)

            :param name: The property-name this bone has in its Skeleton (not the description!)
            :param skel: The :class:`viur.core.skeleton.Skeleton` instance this bone is part of
            :param dbFilter: The current :class:`viur.core.db.Query` instance the filters should be applied to
            :param rawFilter: The dictionary of filters the client wants to have applied
            :returns: The modified :class:`viur.core.db.Query`
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
                property, value = applyFilterHook(dbFilter, "%s <=" % name, rndVal)
                q.filters[property] = value
                q.orders = [(name, db.SortOrder.Descending)]
                queries.append(q)
                # Left Side
                q = db.QueryDefinition(origKind, {}, [])
                property, value = applyFilterHook(dbFilter, "%s >" % name, rndVal)
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
            Tells :class:`viur.core.db.Query` How much entries should be fetched in each subquery.

            :param targetAmount: How many entries shall be returned from db.Query
            :returns: The amount of elements db.Query should fetch on each subquery
        """
        return ceil(targetAmount * self.sliceSize)

    def customMultiQueryMerge(self, dbFilter: db.Query, result: List[db.Entity], targetAmount: int) -> List[db.Entity]:
        """
            Randomly returns 'targetAmount' elements from 'result'

            :param dbFilter: The db.Query calling this function
            :param result: The list of results for each subquery we've run
            :param targetAmount: How many results should be returned from db.Query
            :return: list of elements which should be returned from db.Query
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
