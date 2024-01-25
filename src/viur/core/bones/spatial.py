"""
`spatial` contains
- The `SpatialBone` to handle coordinates
- and `haversine`  to calculate the distance between two points on earth using their latitude and longitude.
"""

import logging
from copy import deepcopy
import typing as t

import math
from math import floor

from viur.core import db
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity


def haversine(lat1, lng1, lat2, lng2):
    """
    Calculate the distance between two points on Earth's surface in meters.

    This function uses the haversine formula to compute the great-circle distance between
    two points on Earth's surface, specified by their latitude and longitude coordinates.
    The haversine formula is particularly useful for small distances on the Earth's surface,
    as it provides accurate results with good performance.

    For more details on the haversine formula, see
    `Haversine formula <https://en.wikipedia.org/wiki/Haversine_formula>`_.

    :param float lat1: Latitude of the first point in decimal degrees.
    :param float lng1: Longitude of the first point in decimal degrees.
    :param float lat2: Latitude of the second point in decimal degrees.
    :param float lng2: Longitude of the second point in decimal degrees.
    :return: Distance between the two points in meters.
    :rtype: float
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
    r"""
    The "SpatialBone" is a specific type of data structure designed to handle spatial data, such as geographical
    coordinates or geometries. This bone would typically be used for representing and storing location-based data,
    like the coordinates of a point of interest on a map or the boundaries of a geographic region.
    This feature allows querying elements near a specific location. Before using, designate the map region for
    which the index should be constructed. To ensure the best accuracy, minimize the region size; using the entire
    world is not feasible since boundary wraps are not executed. GridDimensions indicates the number of sub-regions
    the map will be partitioned into. Results beyond the size of these sub-regions will not be considered during
    searches by this algorithm.

    .. note:: Example:
        When using this feature to find the nearest pubs, the algorithm could be set to consider
        results within 100km but not those 500km away. Setting the sub-region size to roughly
        100km in width and height allows the algorithm to exclude results further than 200km away
        at the database-query-level, significantly enhancing performance and reducing query costs.

        Example region: Germany: ```boundsLat=(46.988, 55.022), boundsLng=(4.997, 15.148)```

    :param Tuple[float, float] boundsLat: The outer bounds (Latitude) of the region we will search in
    :param Tuple[float, float] boundsLng: The outer bounds (Longitude) of the region we will search in
    :param gridDimensions: (Tuple[int, int]) The number of sub-regions the map will be divided in
    """

    type = "spatial"

    def __init__(self, *, boundsLat: tuple[float, float], boundsLng: tuple[float, float],
                 gridDimensions: tuple[int, int], **kwargs):
        """
            Initializes a new SpatialBone.

            :param boundsLat: Outer bounds (Latitude) of the region we will search in.
            :param boundsLng: Outer bounds (Longitude) of the region we will search in.
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
        Calculate and return the size of the sub-regions in terms of fractions of latitude and longitude.

        :return: A tuple containing the size of the sub-regions as (fractions-of-latitude, fractions-of-longitude)
        :rtype: (float, float)
        """
        latDelta = float(self.boundsLat[1] - self.boundsLat[0])
        lngDelta = float(self.boundsLng[1] - self.boundsLng[0])
        return latDelta / float(self.gridDimensions[0]), lngDelta / float(self.gridDimensions[1])

    def isInvalid(self, value: tuple[float, float]) -> str | bool:
        """
        Validate if the given point (latitude, longitude) falls within the specified boundaries.
        Rejects all values outside the defined region.

        :param value: A tuple containing the location of the entry as (latitude, longitude)
        :return: An error description if the value is invalid or False if the value is valid
        :rtype: str | bool
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
        """
        Serialize a single value (latitude, longitude) for storage. If the bone is indexed, calculate
        and add tile information for efficient querying.

        :param value: A tuple containing the location of the entry as (latitude, longitude)
        :param SkeletonInstance skel: The instance of the Skeleton this bone is attached to
        :param str name: The name of this bone
        :param bool parentIndexed: A boolean indicating if the parent bone is indexed
        :return: A dictionary containing the serialized data, including coordinates and tile information (if indexed)
        :rtype: dict | None
        """
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
        """
        Deserialize a single value (latitude, longitude) from the stored data.

        :param val: A dictionary containing the serialized data, including coordinates
        :return: A tuple containing the location of the entry as (latitude, longitude)
        :rtype: Tuple[float, float] | None
        """
        if not val:
            return None
        return val["coordinates"]["lat"], val["coordinates"]["lng"]

    def parseSubfieldsFromClient(self):
        """
        Determines if subfields (latitude and longitude) should be parsed from the client.

        :return: Always returns True, as latitude and longitude are required
        :rtype: bool
        """
        return True  # We'll always get .lat and .lng

    def isEmpty(self, value: t.Any):
        """
        Check if the given raw value is considered empty (either not present or equal to the empty value).

        :param value: The raw value to be checked
        :return: True if the raw value is considered empty, False otherwise
        :rtype: bool
        """
        if not value:
            return True
        if isinstance(value, dict):
            try:
                rawLat = float(value["lat"])
                rawLng = float(value["lng"])
                return (rawLat, rawLng) == self.getEmptyValue()
            except:
                return True
        return value == self.getEmptyValue()

    def getEmptyValue(self) -> tuple[float, float]:
        """
        Returns an empty value for the bone, which represents an invalid position. Use 91.0, 181.0 as a special
        marker for empty, as they are both out of range for Latitude (-90, +90) and Longitude (-180, 180), but will
        be accepted by Vi and Admin.

        :return: A tuple representing an empty value for this bone (91.0, 181.0)
        :rtype: Tuple[float, float]
        """
        return 0.0, 0.0

    def singleValueFromClient(self, value, skel, bone_name, client_data):
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
        rawFilter: dict,
        prefix: t.Optional[str] = None
    ) -> db.Query:
        """
        Parses the client's search filter specified in their request and converts it into a format understood by the
        datastore.
            - Ignore filters that do not target this bone.
            - Safely handle malformed data in rawFilter (this parameter is directly controlled by the client).

        For detailed information on how this geo-spatial search works, see the ViUR documentation.

        :param str name: The property name this bone has in its Skeleton (not the description!)
        :param SkeletonInstance skel: The skeleton this bone is part of
        :param db.Query dbFilter: The current `viur.core.db.Query` instance to which the filters should be applied
        :param dict rawFilter: The dictionary of filters the client wants to have applied
        :param prefix: Optional string, specifying a prefix for the bone's name (default is None)
        :return: The modified `viur.core.db.Query` instance
        :rtype: db.Query
        """
        assert prefix is None, "You cannot use spatial data in a relation for now"
        if name + ".lat" in rawFilter and name + ".lng" in rawFilter:
            try:
                lat = float(rawFilter[name + ".lat"])
                lng = float(rawFilter[name + ".lng"])
            except:
                logging.debug(f"Received invalid values for lat/lng in {name}")
                dbFilter.datastoreQuery = None
                return
            if self.isInvalid((lat, lng)):
                logging.debug(f"Values out of range in {name}")
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

    def calculateInternalMultiQueryLimit(self, dbQuery: db.Query, targetAmount: int):
        """
        Provides guidance to viur.core.db.Query on the number of entries that should be fetched in each subquery.

        :param dbQuery: The `viur.core.db.Query` instance
        :param targetAmount: The desired number of entries to be returned from the db.Query
        :return: The number of elements db.Query should fetch for each subquery
        :rtype: int
        """
        return targetAmount * 2

    def customMultiQueryMerge(self, name, lat, lng, dbFilter: db.Query,
                              result: list[db.Entity], targetAmount: int
                              ) -> list[db.Entity]:
        """
        Randomly returns 'targetAmount' elements from 'result'.

        :param str name: The property-name this bone has in its Skeleton (not the description!)
        :param lat: Latitude of the reference point
        :param lng: Longitude of the reference point
        :param dbFilter: The db.Query instance calling this function
        :param result: The list of results for each subquery that was executed
        :param int targetAmount: The desired number of results to be returned from db.Query
        :return: List of elements to be returned from db.Query
        :rtype: List[db.Entity]
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
        logging.debug(f"""SpatialGuaranteedCorrectness: { dbFilter.customQueryInfo["spatialGuaranteedCorrectness"]}""")
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
        value: t.Any,
        append: bool,
        language: None | str = None
    ) -> bool:
        """
        Sets the value of the bone to the provided 'value'.
        Sanity checks are performed; if the value is invalid, the bone value will revert to its original
        (default) value and the function will return False.

        :param skel: Dictionary with the current values from the skeleton the bone belongs to
        :param boneName: The name of the bone that should be modified
        :param value: The value that should be assigned. Its type depends on the type of the bone
        :param append: If True, the given value will be appended to the existing bone values instead of
            replacing them. Only supported on bones with multiple=True
        :param language: Optional, the language of the value if the bone is language-aware
        :return: A boolean indicating whether the operation succeeded or not
        :rtype: bool
        """
        if append:
            raise ValueError(f"append is not possible on {self.type} bones")
        assert isinstance(value, tuple) and len(value) == 2, "Value must be a tuple of (lat, lng)"
        skel[boneName] = value

    def structure(self) -> dict:
        return super().structure() | {
            "boundslat": self.boundsLat,
            "boundslng": self.boundsLng,
        }
