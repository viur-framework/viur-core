# -*- coding: utf-8 -*-
from server.bones import baseBone
from math import pow, floor, ceil
from server import db
import logging
from math import sqrt

class spatialBone( baseBone ):
	"""
		Holds numeric values.
		Can be used for ints and floats.
		For floats, the precision can be specified in decimal-places.
	"""

	type = "spatial"

	def __init__(self, *args,  **kwargs ):
		"""
			Initializes a new spatialBone.

			:param precision: How may decimal places should be saved. Zero casts the value to int instead of float.
			:type precision: int
			:param min: Minimum accepted value (including).
			:type min: float
			:param max: Maximum accepted value (including).
			:type max: float
		"""
		baseBone.__init__( self,  *args,  **kwargs )
		self.boundsLat = (50.0,60.0)
		self.boundsLng = (10.0,20.0)
		self.gridDimensions = 10.0,12.0

	def getGridSize(self):
		latDelta = self.boundsLat[1]-self.boundsLat[0]
		lngDelta = self.boundsLng[1]-self.boundsLng[0]
		return latDelta/self.gridDimensions[0], lngDelta/self.gridDimensions[1]

	def isInvalid( self, value ):
		if value is None and self.required:
			return "No value entered"
		elif value is None and not self.required:
			return False
		elif value:
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


	def serialize( self, name, entity ):
		if self.value and not self.isInvalid(self.value):
			lat, lng = self.value
			entity.set( name+".lat.val", lat, self.indexed )
			entity.set( name+".lng.val", lng, self.indexed )
			if self.indexed:
				gridSizeLat, gridSizeLng = self.getGridSize()
				tileLat = int(floor((lat-self.boundsLat[0])/gridSizeLat))
				tileLng = int(floor((lng-self.boundsLng[0])/gridSizeLng))
				entity.set( name+".lat.tiles", [tileLat-1,tileLat,tileLat+1], self.indexed )
				entity.set( name+".lng.tiles", [tileLng-1,tileLng,tileLng+1], self.indexed )
		logging.error( entity[name+".lat.tiles"] )
		logging.error( entity[name+".lng.tiles"] )
		return( entity )
		
	def unserialize( self, name, expando ):
		if not name+".lat.val" in expando.keys() or not name+".lng.val":
			self.value = None
			return
		self.value = expando[name+".lat.val"], expando[name+".lng.val"]

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):
		if name+".lat" in rawFilter.keys() and name+".lng" in rawFilter.keys():
			try:
				lat = float(rawFilter[name+".lat"])
				lng = float(rawFilter[name+".lng"])
			except:
				logging.debug("Received invalid values for lat/lng in %s", name)
				dbFilter.datastoreQuery = None
				return
			if self.isInvalid( (lat,lng) ):
				logging.debug("Values out of range in %s", name)
				dbFilter.datastoreQuery = None
				return
			assert self.indexed
			gridSizeLat, gridSizeLng = self.getGridSize()
			tileLat = int(floor((lat-self.boundsLat[0])/gridSizeLat))
			tileLng = int(floor((lng-self.boundsLng[0])/gridSizeLng))
			assert not isinstance( dbFilter.datastoreQuery, db.MultiQuery )
			origQuery = dbFilter.datastoreQuery
			# Lat - Right Side
			q1 = db.DatastoreQuery( kind=dbFilter.getKind() )
			q1[name+".lat.val >="] = lat
			q1[name+".lat.tiles"] = tileLat
			# Lat - Left Side
			q2 = db.DatastoreQuery( kind=dbFilter.getKind() )
			q2[name+".lat.val <"] = lat
			q2[name+".lat.tiles"] = tileLat
			q2.Order( (name+".lat.val", db.DESCENDING) )
			# Lng - Down
			q3 = db.DatastoreQuery( kind=dbFilter.getKind() )
			q3[name+".lng.val >="] = lng
			q3[name+".lng.tiles"] = tileLng
			# Lng - Top
			q4 = db.DatastoreQuery( kind=dbFilter.getKind() )
			q4[name+".lng.val <"] = lng
			q4[name+".lng.tiles"] = tileLng
			q4.Order( (name+".lng.val", db.DESCENDING) )

			dbFilter.datastoreQuery = db.MultiQuery([q1,q2,q3,q4], None)

			dbFilter._customMultiQueryMerge = lambda *args, **kwargs: self.customMultiQueryMerge( name, lat, lng, *args, **kwargs )
			dbFilter._calculateInternalMultiQueryAmount = self.calculateInternalMultiQueryAmount


		#return( super( spatialBone, self ).buildDBFilter( name, skel, dbFilter, rawFilter ) )

	def calculateInternalMultiQueryAmount(self, targetAmount):
		return targetAmount*2

	def customMultiQueryMerge(self, name, lat, lng, dbFilter, result, targetAmount):
		#def calculateDistance(lat1, lat2, lng1, lng2):
		#	return sqrt((lat1-lat2)*(lat1-lat2)+(lng1-lng2)*(lng1-lng2))
		def calculateDistance(item, name, lat, lng):
			"""
			:param item:
			:param lat:
			:param lng:
			:return:
			"""
			return sqrt((item[name+".lat.val"]-lat)*(item[name+".lat.val"]-lat)+(item[name+".lng.val"]-lng)*(item[name+".lng.val"]-lng))

		assert len(result)==4 #There should be exactly one result for each direction
		result = [list(x) for x in result] # Remove the iterators
		latRight, latLeft, lngBottom, lngTop = result
		gridSizeLat, gridSizeLng = self.getGridSize()
		# Calculate the outer bounds we've reached - used to tell to which distance we can
		# prove the result to be correct.
		# If a result further away than this distance there might be missing results before that result
		# If there are no results in a give lane (f.e. because we are close the border and there is no point
		# in between) we choose a arbitrary large value for that lower bound
		limits = [
				(latRight[-1][name+".lat.val"]-lat)*(latRight[-1][name+".lat.val"]-lat) if latRight else 2^31, # Lat - Right Side
				(latLeft[-1][name+".lat.val"]-lat)*(latLeft[-1][name+".lat.val"]-lat) if latLeft else 2^31, # Lat - Left Side
				(lngBottom[-1][name+".lng.val"]-lng)*(lngBottom[-1][name+".lng.val"]-lng) if lngBottom else 2^31, # Lng - Bottom
				(lngTop[-1][name+".lng.val"]-lng)*(lngTop[-1][name+".lng.val"]-lng) if lngTop else 2^31, # Lng - Top
				gridSizeLat,
				gridSizeLng
			]
		dbFilter.spatialGuaranteedCorrectness = min(limits)
		logging.debug("SpatialGuaranteedCorrectness: %s", dbFilter.spatialGuaranteedCorrectness)
		# Filter duplicates
		tmpDict = {}
		for item in (latRight+latLeft+lngBottom+lngTop):
			tmpDict[str(item.key())] = item
		# Build up the final results
		tmpList = [(calculateDistance(x,name,lat,lng),x) for x in tmpDict.values()]
		tmpList.sort( key=lambda x: x[0])
		return [x[1] for x in tmpList[:targetAmount]]