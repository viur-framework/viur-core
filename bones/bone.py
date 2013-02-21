# -*- coding: utf-8 -*-
from google.appengine.api import search
from server.config import conf
import logging

class baseBone(object): # One Bone:
	hasDBField = True
	type = "hidden"
	def __init__( self, descr="", defaultValue=None, required=False, params=None, multiple=False, searchable=False, vfunc=None,  readOnly=False,  visible=True, **kwargs ):
		from server.skeleton import _boneCounter
		#Fallbacks for old non-CamelCase API
		if "defaultvalue" in kwargs.keys():
			defaultValue = kwargs["defaultvalue"]
		if "readonly" in kwargs.keys():
			readOnly = kwargs["readonly"]
		self.descr = descr
		self.required = required
		self.params = params
		self.multiple = multiple
		if self.multiple:
			self.value = []
		else:
			self.value = None
		if defaultValue!=None:
			if callable( defaultValue ):
				self.value = defaultValue( self )
			else:
				self.value = defaultValue
		else:
			if "defaultValue" in dir(self) and callable( self.defaultValue ):
				self.value = self.defaultValue()
		self.searchable = searchable
		if vfunc:
			self.canUse = vfunc
		self.readOnly = readOnly
		self.visible = visible
		self.idx = _boneCounter.count
		_boneCounter.count += 1
		
	def fromClient( self, value ):
		err = self.canUse( value )
		if not err:
			self.value = value
			return( True )
		else:
			return( err )

	def canUse( self, value ):
		if value==None:
			return( "No value entered" )

	def serialize( self, name ):
		if name == "id":
			return( { } )
		else:
			return( {name: self.value } )

	def unserialize( self, name, expando ):
		if name in expando.keys():
			self.value = expando[ name ]
		return( True )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):
		if name == "id" and "id" in rawFilter.keys():
			from server import utils
			if isinstance( rawFilter["id"], list ):
				keyList = [ ndb.Key( urlsafe=key  ) for key in rawFilter["id"] ]
				if keyList:
					dbFilter =	 dbFilter.filter( utils.generateExpandoClass( dbFilter.kind )._key.IN( keyList ) )
			else:
				dbFilter = dbFilter.filter( utils.generateExpandoClass( dbFilter.kind )._key == ndb.Key( urlsafe=rawFilter["id"] ) )
			return( dbFilter )
		myKeys = [ key for key in rawFilter.keys() if key.startswith( name ) ] 
		if len( myKeys ) == 0:
			return( dbFilter )
		if not self.searchable:
			logging.warning( "Invalid searchfilter! %s is not searchable!" % name )
			raise RuntimeError()
		for key in myKeys:
			value = rawFilter[ key ]
			tmpdata = key.partition("$")
			if len( tmpdata ) > 2:
				if isinstance( value, list ):
					continue
				if tmpdata[2]=="lt":
					dbFilter[ tmpdata[0] + " <" ] = value
				elif tmpdata[2]=="gt":
					dbFilter[ tmpdata[0] + " >" ] = value
				elif tmpdata[2]=="lk":
					dbFilter[ tmpdata[0] ] = value
				else:
					dbFilter[ tmpdata[0] ] = value
				#Enforce a working sort-order
				#if "orderdir" in rawFilter.keys()  and rawFilter["orderdir"]=="1":
				#	dbFilter = dbFilter.order( -ndb.GenericProperty( tmpdata[0] ) )
				#else:
				#	dbFilter = dbFilter.order( ndb.GenericProperty( tmpdata[0] ) )
			else:
				if isinstance( value, list ):
					dbFilter = dbFilter.filter( ndb.GenericProperty( key ) in value )
				else:
					dbFilter[ key ] = value
		return( dbFilter )

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		if "orderby" in list(rawFilter.keys()) and rawFilter["orderby"] == name:
			if not self.searchable:
				logging.warning( "Invalid ordering! %s is not searchable!" % name )
				raise RuntimeError()
			if "orderdir" in rawFilter.keys()  and rawFilter["orderdir"]=="1":
				order = ( rawFilter["orderby"], dbFilter.DESCENDING )
			else:
				order = ( rawFilter["orderby"], dbFilter.ASCENDING )
			inEqFilter = [ x for x in dbFilter.keys() if (">" in x[ -3: ] or "<" in x[ -3: ] or "!=" in x[ -4: ] ) ]
			if inEqFilter:
				inEqFilter = inEqFilter[ 0 ][ : inEqFilter[ 0 ].find(" ") ]
				if inEqFilter != order[0]:
					logging.warning("I fixed you query! Impossible ordering changed to %s, %s" % (inEqFilter, order[0]) )
					dbFilter.Order( inEqFilter, order )
				else:
					dbFilter.Order( order )
			else:
				dbFilter.Order( order )
		return( dbFilter )


	def getDBProperty( self, skel ):
		return( ndb.StringProperty() )

	def getTags(self):
		res = []
		if not self.value:
			return( res )
		for line in unicode(self.value).lower().splitlines():
			for key in line.split(" "):
				key = "".join( [ c for c in key if c.lower() in conf["viur.searchValidChars"] ] )
				if key and key not in res and len(key)>3:
					res.append( key )
		return( res )
	
	def getSearchDocumentFields(self, name):
		return( [ search.TextField( name=name, value=unicode( self.value ) ) ] )
