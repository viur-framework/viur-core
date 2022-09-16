from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core import db
import logging, math
from math import pow, floor, ceil
from copy import deepcopy
from math import floor
from typing import Any, Dict, List, Optional, Tuple, Union


def haversine(lat1, lng1, lat2, lng2):
    """
        Calculates the distance between two points on Earth given by (lat1,lng1) and (lat2, lng2) in Meter.
        See https://en.wikipedia.org/wiki/Haversine_formula

        :return: Distance in Meter
    """
    lat1 = math.radians(lat1)
    lng1 = math.radians(lng1)
    lat2 = math.radians(lat2)
    lng2 = math.radians(lng2)
    distLat = lat2 - lat1
    distlng = lng2 - lng1
    d = math.sin(distLat / 2.0) ** 2.0 + math.cos(lat1) * math.cos(lat2) * math.sin(distlng / 2.0) ** 2.0
    return math.atan2(math.sqrt(d), math.sqrt(1 - d)) * 12742000  # 12742000 = Avg. Earth size (6371km) in meters*2


class SpatialBone(BaseBone):
    """
        Allows to query by Elements close to a given position.
        Prior to use, you must specify for which region of the map the index should be build.
        This region should be as small as possible for best accuracy. You cannot use the whole world, as
        no boundary wraps are been performed.
        GridDimensions specifies into how many sub-regions the map will be split. Results further away than the
        size of these sub-regions won't be considered within a search by this algorithm.

        Example:
            If you use this bone to query your data for the nearest pubs, you might want to this algorithm
            to consider results up to 100km distance, but not results that are 500km away.
            Setting the size of these sub-regions to roughly 100km width/height allows this algorithm
            to exclude results further than 200km away on database-query-level, therefore drastically
            improving performance and reducing costs per query.

        Example region: Germany: boundsLat=(46.988, 55.022), boundsLng=(4.997, 15.148)
    """

    type = "spatial"

    def __init__(self, *, boundsLat: Tuple[float, float], boundsLng: Tuple[float, float], gridDimensions: Tuple[int, int], **kwargs):
        """
            Initializes a new SpatialBone.

            :param boundsLat: Outer bounds (Latitude) of the region we will search in.
            :param boundsLng: Outer bounds (Latitude) of the region we will search in.
            :param gridDimensions: Number of sub-regions the map will be divided in
        """
        super().__init__(**kwargs)
        assert isinstance(boundsLat, tuple) and len(boundsLat) == 2, "boundsLat must be a tuple of (float, float)"
        assert isinstance(boundsLng, tuple) and len(boundsLng) == 2, "boundsLng must be a tuple of (float, float)"
        assert isinstance(gridDimensions, tuple) and len(
            gridDimensions) == 2, "gridDimensions must be a tuple of (int, int)"
        # Checks if boundsLat and boundsLng have possible values
        # See https://docs.mapbox.com/help/glossary/lat-lon/
        if not -90 <= boundsLat[0] <= 90:
            raise ValueError(f"boundsLat[0] must be between -90 and 90. Got {boundsLat[0]!r}")
        if not -90 <= boundsLat[1] <= 90:
            raise ValueError(f"boundsLat[1] must be between -90 and 90. Got {boundsLat[1]!r}")
        if not -180 <= boundsLng[0] <= 180:
            raise ValueError(f"boundsLng[0] must be between -180 and 180. Got {boundsLng[0]!r}")
        if not -180 <= boundsLng[1] <= 180:
            raise ValueError(f"boundsLng[1] must be between -180 and 180. Got {boundsLng[1]!r}")
        assert not (self.indexed and self.multiple), "Spatial-Bone cannot be indexed when multiple"
        self.boundsLat = boundsLat
        self.boundsLng = boundsLng
        self.gridDimensions = gridDimensions

    def getGridSize(self):
        """
            :return: the size of our sub-regions in (fractions-of-latitude, fractions-of-longitude)
            :rtype: (float, float)
        """
        latDelta = float(self.boundsLat[1] - self.boundsLat[0])
        lngDelta = float(self.boundsLng[1] - self.boundsLng[0])
        return latDelta / float(self.gridDimensions[0]), lngDelta / float(self.gridDimensions[1])

    def isInvalid(self, value: Tuple[float, float]) -> Union[str, bool]:
        """
            Tests, if the point given by 'value' is inside our boundaries.
            We'll reject all values outside that region.
            :param value: (latitude, longitude) of the location of this entry.
            :return: An error-description or False if the value is valid
            :rtype: str | False
        """
        try:
            lat, lng = value
        except:
            return "Invalid value entered"
        if lat < self.boundsLat[0] or lat > self.boundsLat[1]:
            return "Latitude out of range"
        elif lng < self.boundsLng[0] or lng > self.boundsLng[1]:
            return "Longitude out of range"
        else:
            return False

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        if not value:
            return None
        lat, lng = value
        res = {
            "coordinates": {
                "lat": lat,
                "lng": lng,
            }
        }
        indexed = self.indexed and parentIndexed
        if indexed:
            gridSizeLat, gridSizeLng = self.getGridSize()
            tileLat = int(floor((lat - self.boundsLat[0]) / gridSizeLat))
            tileLng = int(floor((lng - self.boundsLng[0]) / gridSizeLng))
            res["tiles"] = {
                "lat": [tileLat - 1, tileLat, tileLat + 1],
                "lng": [tileLng - 1, tileLng, tileLng + 1],
            }
        return res

    def singleValueUnserialize(self, val):
        if not val:
            return None
        return val["coordinates"]["lat"], val["coordinates"]["lng"]

    def parseSubfieldsFromClient(self):
        return True  # We'll always get .lat and .lng

    def isEmpty(self, rawValue: Any):
        if not rawValue:
            return True
        if isinstance(rawValue, dict):
            try:
                rawLat = float(rawValue["lat"])
                rawLng = float(rawValue["lng"])
                return (rawLat, rawLng) == self.getEmptyValue()
            except:
                return True
        return rawValue == self.getEmptyValue()

    def getEmptyValue(self) -> Tuple[float, float]:
        """
            If you need a special marker for empty, use 91.0, 181.0.
            These are both out of range for Latitude (-90, +90) and Longitude (-180, 180) but will be accepted
            by Vi and Admin
        """
        return 0.0, 0.0

    def singleValueFromClient(self, value: Dict, skel: str, name: str, origData: Dict):
        """
            Reads a value from the client.
            If this value is valid for this bone,
            store this value and return None.
            Otherwise our previous value is
            left unchanged and an error-message
            is returned.

            :param name: Our name in the skeleton
            :param value: *User-supplied* request-data
        """
        rawLat = value.get("lat", None)
        rawLng = value.get("lng", None)
        if rawLat is None and rawLng is None:
            return self.getEmptyValue(), [
                ReadFromClientError(ReadFromClientErrorSeverity.NotSet, "Field not submitted")]
        elif rawLat is None or rawLng is None:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Empty, "No value submitted")]
        try:
            rawLat = float(rawLat)
            rawLng = float(rawLng)
            # Check for NaNs
            assert rawLat == rawLat
            assert rawLng == rawLng
        except:
            return self.getEmptyValue(), [
                ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")]
        err = self.isInvalid((rawLat, rawLng))
        if err:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
        return (rawLat, rawLng), None


    def buildDBFilter(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: Dict,
        prefix: Optional[str] = None
    ) -> db.Query:
        """
            Parses the searchfilter a client specified in his Request into
            something understood by the datastore.
            This function must:

                * Ignore all filters not targeting this bone
                * Safely handle malformed data in rawFilter
                    (this parameter is directly controlled by the client)

            For detailed information, how this geo-spatial search works, see the ViUR documentation.

            :param name: The property-name this bone has in its Skeleton (not the description!)
            :param skel: The :class:`viur.core.db.Query` this bone is part of
            :param dbFilter: The current :class:`viur.core.db.Query` instance the filters should be applied to
            :param rawFilter: The dictionary of filters the client wants to have applied
            :returns: The modified :class:`viur.core.db.Query`
        """
        assert prefix is None, "You cannot use spatial data in a relation for now"
        if name + ".lat" in rawFilter and name + ".lng" in rawFilter:
            try:
                lat = float(rawFilter[name + ".lat"])
                lng = float(rawFilter[name + ".lng"])
            except:
                logging.debug("Received invalid values for lat/lng in %s", name)
                dbFilter.datastoreQuery = None
                return
            if self.isInvalid((lat, lng)):
                logging.debug("Values out of range in %s", name)
                dbFilter.datastoreQuery = None
                return
            gridSizeLat, gridSizeLng = self.getGridSize()
            tileLat = int(floor((lat - self.boundsLat[0]) / gridSizeLat))
            tileLng = int(floor((lng - self.boundsLng[0]) / gridSizeLng))
            assert isinstance(dbFilter.queries, db.QueryDefinition)  # Not supported on multi-queries
            origQuery = dbFilter.queries
            # Lat - Right Side
            q1 = deepcopy(origQuery)
            q1.filters[name + ".coordinates.lat >="] = lat
            q1.filters[name + ".tiles.lat ="] = tileLat
            q1.orders = [(name + ".coordinates.lat", db.SortOrder.Ascending)]
            # Lat - Left Side
            q2 = deepcopy(origQuery)
            q2.filters[name + ".coordinates.lat <"] = lat
            q2.filters[name + ".tiles.lat ="] = tileLat
            q2.orders = [(name + ".coordinates.lat", db.SortOrder.Descending)]
            # Lng - Down
            q3 = deepcopy(origQuery)
            q3.filters[name + ".coordinates.lng >="] = lng
            q3.filters[name + ".tiles.lng ="] = tileLng
            q3.orders = [(name + ".coordinates.lng", db.SortOrder.Ascending)]
            # Lng - Top
            q4 = deepcopy(origQuery)
            q4.filters[name + ".coordinates.lng <"] = lng
            q4.filters[name + ".tiles.lng ="] = tileLng
            q4.orders = [(name + ".coordinates.lng", db.SortOrder.Descending)]
            dbFilter.queries = [q1, q2, q3, q4]
            dbFilter._customMultiQueryMerge = lambda *args, **kwargs: self.customMultiQueryMerge(name, lat, lng, *args,
                                                                                                 **kwargs)
            dbFilter._calculateInternalMultiQueryLimit = self.calculateInternalMultiQueryLimit

    # return super().buildDBFilter(name, skel, dbFilter, rawFilter)

    def calculateInternalMultiQueryLimit(self, dbQuery: db.Query, targetAmount: int):
        """
            Tells :class:`viur.core.db.Query` How much entries should be fetched in each subquery.

            :param targetAmount: How many entries shall be returned from db.Query
            :returns: The amount of elements db.Query should fetch on each subquery
        """
        return targetAmount * 2

    def customMultiQueryMerge(self, name, lat, lng, dbFilter: db.Query,
                              result: List[db.Entity], targetAmount: int
                              ) -> List[db.Entity]:
        """
            Randomly returns 'targetAmount' elements from 'result'

            :param name:
            :param lat:
            :param lng:
            :param dbFilter: The db.Query calling this function
            :param result: The list of results for each subquery we've run
            :param targetAmount: How many results should be returned from db.Query
            :return: List of elements which should be returned from db.Query
        """
        assert len(result) == 4  # There should be exactly one result for each direction
        result = [list(x) for x in result]  # Remove the iterators
        latRight, latLeft, lngBottom, lngTop = result
        gridSizeLat, gridSizeLng = self.getGridSize()
        # Calculate the outer bounds we've reached - used to tell to which distance we can
        # prove the result to be correct.
        # If a result further away than this distance there might be missing results before that result
        # If there are no results in a give lane (f.e. because we are close the border and there is no point
        # in between) we choose a arbitrary large value for that lower bound
        expectedAmount = self.calculateInternalMultiQueryLimit(dbFilter,
                                                               targetAmount)  # How many items we expect in each direction
        limits = [
            haversine(latRight[-1][name]["coordinates"]["lat"], lng, lat, lng) if latRight and len(
                latRight) == expectedAmount else 2 ** 31,  # Lat - Right Side
            haversine(latLeft[-1][name]["coordinates"]["lat"], lng, lat, lng) if latLeft and len(
                latLeft) == expectedAmount else 2 ** 31,  # Lat - Left Side
            haversine(lat, lngBottom[-1][name]["coordinates"]["lng"], lat, lng) if lngBottom and len(
                lngBottom) == expectedAmount else 2 ** 31,  # Lng - Bottom
            haversine(lat, lngTop[-1][name]["coordinates"]["lng"], lat, lng) if lngTop and len(
                lngTop) == expectedAmount else 2 ** 31,  # Lng - Top
            haversine(lat + gridSizeLat, lng, lat, lng),
            haversine(lat, lng + gridSizeLng, lat, lng)
        ]
        dbFilter.customQueryInfo["spatialGuaranteedCorrectness"] = min(limits)
        logging.debug("SpatialGuaranteedCorrectness: %s", dbFilter.customQueryInfo["spatialGuaranteedCorrectness"])
        # Filter duplicates
        tmpDict = {}
        for item in (latRight + latLeft + lngBottom + lngTop):
            tmpDict[str(item.key)] = item
        # Build up the final results
        tmpList = [(haversine(x[name]["coordinates"]["lat"], x[name]["coordinates"]["lng"], lat, lng), x) for x in
                   tmpDict.values()]
        tmpList.sort(key=lambda x: x[0])
        return [x[1] for x in tmpList[:targetAmount]]

    def setBoneValue(
        self,
        skel: 'SkeletonInstance',
        boneName: str,
        value: Any,
        append: bool,
        language: Union[None, str] = None
    ) -> bool:
        """
            Set our value to 'value'.
            Santy-Checks are performed; if the value is invalid, we flip our value back to its original
            (default) value and return false.

            :param skel: Dictionary with the current values from the skeleton we belong to
            :param boneName: The Bone which should be modified
            :param value: The value that should be assigned. It's type depends on the type of that bone
            :param append: If true, the given value is appended to the values of that bone instead of
                replacing it. Only supported on bones with multiple=True
            :return: Wherever that operation succeeded or not.
        """
        if append:
            raise ValueError("append is not possible on %s bones" % self.type)
        assert isinstance(value, tuple) and len(value) == 2, "Value must be a tuple of (lat, lng)"
        skel[boneName] = value
