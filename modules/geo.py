# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server.applications.list import List
from server.bones import *
from google.appengine.ext import db
from server import session, errors
import urllib
from google.appengine.api import search

class GeoSkel( Skeleton ):
	name = stringBone( descr="Name", indexed=True, required=True, searchable=True )
	address = stringBone( descr="Street and House Number", indexed=True, required=True )
	zipcode = stringBone( descr="Zipcode", indexed=True, required=True )
	city = stringBone( descr="City", indexed=True, required=True)
	country = selectCountryBone( descr="Country", codes=selectCountryBone.ISO2, required=True )
	latitude = numericBone( descr="Latitude", required=False, precision=8 )
	longitude = numericBone( descr="Longitude", required=False, precision=8 )
	
	def fromClient( self, data ):
		"""
		Try to retrive Lat/Long Coordinates for the given address
		"""
		res = super( GeoSkel, self ).fromClient( data )
		if data and not self.latitude.value and not self.longitude.value:
			try:
				addr = "%s, %s, %s, %s" % ( self.address.value, self.zipcode.value, self.city.value, self.country.value )
				# Encode query string into URL
				url = 'http://maps.google.com/?q=' + urllib.quote(addr.lower().encode("ascii","xmlcharrefreplace")) + '&output=js'
				# Get XML location
				xml = urllib.urlopen(url).read()
				if not '<error>' in xml:
					# Strip lat/long coordinates from XML
					lat,lng = 0.0,0.0
					center = xml[xml.find('{center')+10:xml.find('}',xml.find('{center'))]
					center = center.replace('lat:','').replace('lng:','')
					lat, lng = center.split(',')
					self.latitude.value = float( "".join( [x for x in lat if x in "01234567890."]) )
					self.longitude.value = float( "".join( [x for x in lng if x in "01234567890."]) )
			except:
				pass
		return( res )
	
	def getSearchDocumentFields( self, fields ):
		fields.append( search.GeoField(name='latlong', value=search.GeoPoint(self.latitude.value, self.longitude.value)) )
		return( fields )

class Geo( List ): 
	adminInfo = {	"name": "Geo", #Name of this modul, as shown in Apex (will be translated at runtime)
				"handler": "list",  #Which handler to invoke
				"icon": "icons/modules/geo.png", #Icon for this modul
				"formatstring": "$(name)", 
				"filters" : { 	
							None: { "filter":{ },
									"icon":"icons/modules/geo.png",
									"columns":["name", "address", "zipcode", "city", "country"]
							},
					}
				}
	viewSkel = GeoSkel
	addSkel = GeoSkel
	editSkel = GeoSkel

