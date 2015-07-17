# -*- coding: utf-8 -*-
from server.bones import baseBone
from math import pow, floor, ceil
from server import db
import logging
import math

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
	distLat = lat2-lat1
	distlng = lng2-lng1
	d = math.sin(distLat/2.0)**2.0+math.cos(lat1)*math.cos(lat2)*math.sin(distlng/2.0)**2.0
	return math.atan2(math.sqrt(d),math.sqrt(1-d))*12742000 # 12742000 = Avg. Earth size (6371km) in meters*2


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
			return math.sqrt((item[name+".lat.val"]-lat)*(item[name+".lat.val"]-lat)+(item[name+".lng.val"]-lng)*(item[name+".lng.val"]-lng))

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
				haversine(latRight[-1][name+".lat.val"], lng, lat, lng) if latRight else 2^31, # Lat - Right Side
				haversine(latLeft[-1][name+".lat.val"], lng, lat, lng) if latLeft else 2^31, # Lat - Left Side
				haversine(lat, lngBottom[-1][name+".lng.val"], lat, lng) if lngBottom else 2^31, # Lng - Bottom
				haversine(lat, lngTop[-1][name+".lng.val"], lat, lng) if lngTop else 2^31, # Lng - Top
				haversine(lat+gridSizeLat,lng,lat,lng),
				haversine(lat,lng+gridSizeLng,lat,lng)
			]
		dbFilter.customQueryInfo["spatialGuaranteedCorrectness"] = min(limits)
		logging.error("SpatialGuaranteedCorrectness: %s", dbFilter.customQueryInfo["spatialGuaranteedCorrectness"])
		# Filter duplicates
		tmpDict = {}
		for item in (latRight+latLeft+lngBottom+lngTop):
			tmpDict[str(item.key())] = item
		# Build up the final results

		tmpList = [(haversine(x[name+".lat.val"],x[name+".lng.val"],lat,lng),x) for x in tmpDict.values()]
		#tmpList = [(calculateDistance(x,name,lat,lng),x) for x in tmpDict.values()]
		tmpList.sort( key=lambda x: x[0])
		return [x[1] for x in tmpList[:targetAmount]]