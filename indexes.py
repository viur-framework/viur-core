# -*- coding: utf-8 -*-
import logging
import json
from datetime import datetime
from hashlib import sha256


class IndexMannager:
	"""Allows efficient pagination for a small specified set of querys.
	This works *only* if the number of different querys is limited.
	Otherwise use the built-in page parameter for small resultsets and few pages.
	If you have lots of different querys and large resultsets you can only generate next/previous Pagelinks on the fly.
	
	Note: The refreshAll Method is missing - intentionally. Whenever data changes you have to call refreshIndex for each affected Index.
	As long as you can name them, their number is limited and everything is fine :)

	"""

	_dbType = "viur_indexes"
	
	def __init__(self, pageSize=10, maxPages=100):
		self.pageSize = pageSize
		self.maxPages = maxPages
		self._cache = {}
	
	def keyFromQuery(self, query ):
		"""
		Derives a unique Database-Key from a given query.
		This Key is stable regardless in which order the filter have been applied
		@param query: Query to derive key from
		@type query: DB.Query
		@returns: string
		"""
		#origFilter = [ (x, y) for x, y in query._get_query().items() ]
		#for k, v in query._Query__orderings:
		#	origFilter.append( ("__%s ="%k, v) )
		#origFilter.sort( key=lambda x: x[0] )
		#filterKey = "".join( ["%s%s" % (x, y) for x, y in origFilter ] )
		## FIXME: this is currently unrelieable due to the switch to NDB
		## TODO: figure out a safe way to implement this; this is currently a bad hack
		filterKey = str( query.filters )+str( query.orders )
		return( sha256( filterKey ).hexdigest() )

	def getOrBuildIndex(self, origQuery ):
		"""
		Builds a specific index based on origQuery AND local variables (self.indexPage and self.indexMaxPage)
		Returns a list of starting-cursors for each page.
		You probably shouldnt call this directly. Use cursorForQuery.
		@param origQuery: Query to build the index for
		@type origQuery: db.Query
		@param key: DB-Key to save the index to
		@type key: string
		@returns: []
		"""
		key = self.keyFromQuery( origQuery )
		if key in self._cache.keys(): #We have it cached
			return( self._cache[ key ] )
		#We dont have it cached - try to load it from DB
		index = generateExpandoClass( self._dbType ).get_by_id( key )
		if index: #This index was allready there
			res = json.loads( index.data )
			self._cache[ key ] = res
			return( res )
		#We dont have this index yet.. Build it
		#Clone the original Query
		query = generateExpandoClass( origQuery._Query__kind ).query()
		if origQuery.filters:
			query = query.filter( origQuery.filters )
		if origQuery.orders:
			query = query.order( origQuery.orders )
		#Build-Up the index
		items, cursor, more = query.fetch_page(self.pageSize)
		res = [ None ] #The first page donst have any cursor
		while( more ):
			if len( res ) > self.maxPages:
				break
			if more:
				res.append( cursor.urlsafe() )
			items, cursor, more = query.fetch_page(self.pageSize, start_cursor=cursor)
		generateExpandoClass( self._dbType ).get_or_insert( key, data=json.dumps( res ), creationdate=datetime.now() )
		return( res )

	def cursorForQuery(self, query, page ):
		"""
		Returns the startingcursor for the given query and page using an index.
		
		WARNING: Make sure the maximum count of different querys are limited!
		If an attacker can choose the query freely, bad things will happen!
		
		@param query: Query to get the cursor for
		@type query: db.Query
		@param page: Page the user wants to retrive
		@type page: int
		@returns: String-Cursor or None if no cursor is appicable
		"""
		return( None )
		page = int(page)
		pages = self.getOrBuildIndex( query )
		if page>0 and len( pages )>page:
			return( ndb.Cursor( urlsafe=pages[ page ] ) )
		else:
			return( None )
	
	def getPages(self, query ):
		"""
			Returns a list of all starting-cursors for this query.
			The first element is always None as the first page dosnt
			have any start-cursor
		"""
		return( [None] )
		return( self.getOrBuildIndex( query ) )
		
			
	def refreshIndex(self, query ):
		"""
		Refreshes the Index for the given query
		(Actually it removes it from the db so it gets rebuild on next use)
		
		@param query: Query for which the index should be refreshed
		@type query: db.Query
		"""
		return
		key = self.keyFromQuery( query )
		index = generateExpandoClass( self._dbType ).get_by_id( key )
		if index:
			index.key.delete()
		if key in self._cache.keys():
			del self._cache[ key ]
