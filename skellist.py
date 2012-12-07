# -*- coding: utf-8 -*-
from server.bones import baseBone
from server import utils
from google.appengine.ext import ndb
from google.appengine.api import memcache
import logging

class Skellist( list ): # Our all-in-one lib
	def __init__( self, viewSkel ):
		self.viewSkel = viewSkel
		self.cursor = None
		self.hasMore = False
		pass
	
	def fromDB( self, queryObj ):
		skel = self.viewSkel()
		if isinstance( queryObj, ndb.query.Query ):
			if queryObj.cursor:
				res, cursor, more = queryObj.fetch_page( queryObj.limit, start_cursor=queryObj.cursor )
			else:
				res, cursor, more = queryObj.fetch_page( queryObj.limit )
			if cursor:
				self.cursor = cursor.urlsafe()
			self.hasMore = more
		else: #Hopefully this is a list of results or an interator
			res = queryObj
		for data in res:
			_skel = self.viewSkel()
			if data.key.kind()!=skel._expando._get_kind(): #The Class for this query has been changed (relation!)
				_skel.fromDB( data.key.parent().urlsafe() )
			else:
				_skel.setValues( data )
			self.append( _skel )
		return

