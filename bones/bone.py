# -*- coding: utf-8 -*-
from google.appengine.api import search
from server.config import conf
from server import db
import logging

class baseBone(object): # One Bone:
	hasDBField = True
	type = "hidden"
	def __init__(	self, descr="", defaultValue=None, required=False, params=None, multiple=False,
			indexed=False, searchable=False, vfunc=None, readOnly=False, visible=True, **kwargs ):
		"""
			Initializes a new Bone.
			@param descr: Textual, human-readable description of that bone. Will be translated.
			@type descr: String
			@param defaultValue: If set, this bone will be preinitialized with this value
			@type defaultValue: mixed
			@param required: If True, the user must enter a valid value for this bone
				(the server refuses to save the skeleton otherwise)
			@type required: Bool
			@param params: Optional dictionary of custom values to pass along with this bone.
				This dictionary will be avaiable in the admin aswell as templates rendered
				by the jinja2-render. Can be used to specifiy project-depended informations
				used to configure the apperance of this bone.
			@type params: Dict or None
			@param multiple: If True, multiple values can be given. (ie. n:m relations instead of n:1)
				Note: This flag is not supported by all bones (fe. selectOneBone)
			@type multiple: Bool
			@param indexed: If True, this bone will be included in indexes. This is needed if you
				want to run queries against this bone. If False, it will save datastore write-ops.
			@type indexed: Bool
			@param searchable: If True, this bone will be included in the fulltext search. Can be used
				without the need of also been indexed.
			@type searchable: Bool
			@param vfunc: If given, a callable validating the user-supplied value for this bone. This
				callable must return None if the value is valid, a String containing an meaningfull
				error-message for the user otherwise.
			@type vfunc: Callable
			@param readOnly: If True, the user is unable to change the value of this bone. If a value for
				this bone is given along the POST-Request during Add/Edit, this value will be ignored.
				Its still possible for the developer to modify this value by assigning skel.bone.value.
			@type readOnly: Bool
			@param visible: If False, the value of this bone should be hidden from the user. This does *not*
				protect the value from beeing exposed in a template, nor from being transfered to the
				client (ie to the admin or as hidden-value in html-forms)
				Again: This is just a hint. It cannot be used as a security precaution.
			@type visible: Bool
		"""
		from server.skeleton import _boneCounter
		#Fallbacks for old non-CamelCase API
		for x in ["defaultvalue", "readonly"]:
			if x in kwargs.keys():
				raise NotImplementedError("%s is not longer supported" % x )
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
		self.indexed = indexed
		self.searchable = searchable
		if vfunc:
			self.canUse = vfunc
		self.readOnly = readOnly
		self.visible = visible
		self.idx = _boneCounter.count
		_boneCounter.count += 1
		
	def fromClient( self, value ):
		"""
			Reads a value from the client.
			If this value is valis for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.
		"""
		err = self.canUse( value )
		if not err:
			self.value = value
			return( True )
		else:
			return( err )

	def canUse( self, value ):
		"""
			Returns None if the value would be valid for
			this bone, an error-message otherwise.
		"""
		if value==None:
			return( "No value entered" )

	def serialize( self, name, entity ):
		"""
			Serializes this bone into something we
			can write into the datastore.
			
			@param name: The property-name this bone has in its Skeleton (not the description!)
			@type name: String
			@returns: Dict
		"""
		if name != "id":
			entity.set( name, self.value, self.indexed )
		return( entity )

	def unserialize( self, name, expando ):
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.
			@param name: The property-name this bone has in its Skeleton (not the description!)
			@type name: String
			@param expando: An instance of the dictionary-like db.Entity class
			@type expando: db.Entity
		"""
		if name in expando.keys():
			self.value = expando[ name ]
		return( True )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):
		"""
			Parses the searchfilter a client specified in his Request into
			something understood by the datastore.
			This function must:
				- Ignore all filters not targeting this bone
				- Safely handle malformed data in rawFilter 
				(this parameter is directly controlled by the client)
			
			@param name: The property-name this bone has in its Skeleton (not the description!)
			@type name: String
			@param skel: The skeleton this bone is part of
			@type skel: Skeleton
			@param dbFilter: The current db.Query instance the filters should be applied to
			@type db.Query
			@param rawFilter: The dictionary of filters the client wants to have applied
			@type rawFilter: Dict
			@returns: The modified dbFilter
		"""
		if name == "id" and "id" in rawFilter.keys():
			from server import utils
			if isinstance( rawFilter["id"], list ):
				keyList = [ db.Key( key  ) for key in rawFilter["id"] ]
				if keyList:
					origQuery = dbFilter.datastoreQuery
					try:
						dbFilter.datastoreQuery = db.MultiQuery( [db.DatastoreQuery( dbFilter.getKind(), filters={ db.KEY_SPECIAL_PROPERTY: x } ) for x in keyList ], () )
					except db.BadKeyError: #Invalid key
						raise RuntimeError()
					except UnicodeEncodeError: # Also invalid key
						raise RuntimeError()
					for k, v in origQuery.items():
						dbFilter.filter( k, v )
			else:
				try:
					dbFilter.filter( db.KEY_SPECIAL_PROPERTY, db.Key( rawFilter["id"] ) )
				except db.BadKeyError: #This cant work
					raise RuntimeError()
				except UnicodeEncodeError: # Also invalid key
					raise RuntimeError()
			return( dbFilter )
		myKeys = [ key for key in rawFilter.keys() if key.startswith( name ) ] 
		if len( myKeys ) == 0:
			return( dbFilter )
		if not self.indexed:
			logging.warning( "Invalid searchfilter! %s is not indexed!" % name )
			raise RuntimeError()
		for key in myKeys:
			value = rawFilter[ key ]
			tmpdata = key.partition("$")
			if len( tmpdata ) > 2:
				if isinstance( value, list ):
					continue
				if tmpdata[2]=="lt":
					dbFilter.filter( tmpdata[0] + " <" , value )
				elif tmpdata[2]=="gt":
					dbFilter.filter( tmpdata[0] + " >",  value )
				elif tmpdata[2]=="lk":
					dbFilter.filter( tmpdata[0],  value )
				else:
					dbFilter.filter( tmpdata[0],  value )
			else:
				if isinstance( value, list ):
					dbFilter.filter( ndb.GenericProperty( key ) in value )
				else:
					dbFilter.filter( key, value )
		return( dbFilter )

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		"""
			Same as buildDBFilter, but this time its not about filtering
			the results, but by sorting them.
			Again: rawFilter is controlled by the client, so you *must* expect and safely hande
			malformed data!
			
			@param name: The property-name this bone has in its Skeleton (not the description!)
			@type name: String
			@param skel: The skeleton this bone is part of
			@type skel: Skeleton
			@param dbFilter: The current db.Query instance the filters should be applied to
			@type db.Query
			@param rawFilter: The dictionary of filters the client wants to have applied
			@type rawFilter: Dict
			@returns: The modified dbFilter
		"""
		if "orderby" in list(rawFilter.keys()) and rawFilter["orderby"] == name:
			if not self.indexed:
				logging.warning( "Invalid ordering! %s is not indexed!" % name )
				raise RuntimeError()
			if "orderdir" in rawFilter.keys()  and rawFilter["orderdir"]=="1":
				order = ( rawFilter["orderby"], db.DESCENDING )
			else:
				order = ( rawFilter["orderby"], db.ASCENDING )
			inEqFilter = [ x for x in dbFilter.datastoreQuery.keys() if (">" in x[ -3: ] or "<" in x[ -3: ] or "!=" in x[ -4: ] ) ]
			if inEqFilter:
				inEqFilter = inEqFilter[ 0 ][ : inEqFilter[ 0 ].find(" ") ]
				if inEqFilter != order[0]:
					logging.warning("I fixed you query! Impossible ordering changed to %s, %s" % (inEqFilter, order[0]) )
					dbFilter.order( (inEqFilter, order) )
				else:
					dbFilter.order( order )
			else:
				dbFilter.order( order )
		return( dbFilter )


	def getSearchTags(self):
		"""
			Returns a list of Strings which will be included in the
			fulltext-index for this bone.
			Note: This function gets only called, if the ViUR internal
			fulltext-search is used. If you enable the search-API
			by setting a searchIndex on the skeleton, getSearchDocumentFields
			is called instead.
			
			@returns: List of Strings
		"""
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
		"""
			Returns a list of search-fields (GAE search API) for this bone.
		"""
		return( [ search.TextField( name=name, value=unicode( self.value ) ) ] )
