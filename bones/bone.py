# -*- coding: utf-8 -*-
from google.appengine.api import search
from server.config import conf
from server import db
import logging
import hashlib
import copy


__systemIsIntitialized_ = False

def setSystemInitialized():
	global __systemIsIntitialized_
	from server.skeleton import iterAllSkelClasses, skeletonByKind
	__systemIsIntitialized_ = True
	for skelCls in iterAllSkelClasses():
		skelCls.setSystemInitialized()

def getSystemInitialized():
	global __systemIsIntitialized_
	return __systemIsIntitialized_


class boneFactory(object):
	IDX = 1

	def __init__(self, cls, args, kwargs):
		super(boneFactory, self).__init__()
		self.cls = cls
		self.args = args
		self.kwargs = kwargs
		self.idx = boneFactory.IDX
		boneFactory.IDX += 1

	def __call__(self, *args, **kwargs):
		tmpDict = self.kwargs.copy()
		tmpDict.update(kwargs)
		return self.cls(*(self.args + args), **tmpDict)

	def __repr__(self):
		return "%sFactory" % self.cls.__name__


class baseBone(object): # One Bone:
	hasDBField = True
	type = "hidden"
	isClonedInstance = False


	#def __new__(cls, *args, **kwargs):
	#	if getSystemInitialized():
	#		return super(baseBone, cls).__new__(cls, *args, **kwargs)
	#	else:
	#		return boneFactory(cls, args, kwargs)

	def __init__(	self, descr="", defaultValue=None, required=False, params=None, multiple=False,
			indexed=False, searchable=False, vfunc=None, readOnly=False, visible=True, unique=False, **kwargs ):
		"""
			Initializes a new Bone.

			:param descr: Textual, human-readable description of that bone. Will be translated.
			:type descr: str
			:param defaultValue: If set, this bone will be preinitialized with this value
			:type defaultValue: mixed
			:param required: If True, the user must enter a valid value for this bone (the server refuses to save the
				skeleton otherwise)
			:type required: bool
			:param multiple: If True, multiple values can be given. (ie. n:m relations instead of n:1)
			:type multiple: bool
			:param indexed: If True, this bone will be included in indexes. This is needed if you
				want to run queries against this bone. If False, it will save datastore write-ops.
			:type indexed: bool
			:param searchable: If True, this bone will be included in the fulltext search. Can be used
				without the need of also been indexed.
			:type searchable: bool
			:param vfunc: If given, a callable validating the user-supplied value for this bone. This
				callable must return None if the value is valid, a String containing an meaningfull
				error-message for the user otherwise.
			:type vfunc: callable
			:param readOnly: If True, the user is unable to change the value of this bone. If a value for
				this bone is given along the POST-Request during Add/Edit, this value will be ignored.
				Its still possible for the developer to modify this value by assigning skel.bone.value.
			:type readOnly: bool
			:param visible: If False, the value of this bone should be hidden from the user. This does *not*
				protect the value from beeing exposed in a template, nor from being transfered to the
				client (ie to the admin or as hidden-value in html-forms)
				Again: This is just a hint. It cannot be used as a security precaution.
			:type visible: bool

			.. NOTE::
				The kwarg 'multiple' is not supported by all bones

		"""
		from server.skeleton import _boneCounter
		#Fallbacks for old non-CamelCase API
		for x in ["defaultvalue", "readonly"]:
			if x in kwargs:
				raise NotImplementedError("%s is not longer supported" % x )
		self.isClonedInstance = getSystemInitialized()
		self.descr = descr
		self.required = required
		self.params = params
		self.multiple = multiple
		self.defaultValue = defaultValue
		self.indexed = indexed
		self.searchable = searchable
		if vfunc:
			self.isInvalid = vfunc
		self.readOnly = readOnly
		self.visible = visible
		self.unique = unique
		self.idx = _boneCounter.count
		if "canUse" in dir( self ):
			raise AssertionError("canUse is deprecated! Use isInvalid instead!")
		_boneCounter.count += 1

	def setSystemInitialized(self):
		"""
			Can be overriden to initialize properties that depend on the Skeleton system being initialized
		"""
		pass


	def getDefaultValue(self):
		if callable(self.defaultValue):
			return self.defaultValue()
		elif isinstance(self.defaultValue, list):
			return self.defaultValue[:]
		elif isinstance(self.defaultValue, dict):
			return
		else:
			return self.defaultValue

	def __setattr__(self, key, value):
		if not self.isClonedInstance and getSystemInitialized() and key!= "isClonedInstance" and not key.startswith("_"):
			raise AttributeError("You cannot modify this Skeleton. Grab a copy using .clone() first")
		super(baseBone, self).__setattr__(key, value)

	def fromClient( self, valuesCache, name, data ):
		"""
			Reads a value from the client.
			If this value is valis for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.

			:param name: Our name in the skeleton
			:type name: String
			:param data: User-supplied request-data
			:type data: dict
			:returns: None or str
		"""
		if name in data:
			value = data[ name ]
		else:
			value = None
		err = self.isInvalid( value )
		if not err:
			valuesCache[name] = value
			return( True )
		else:
			return( err )

	def isInvalid( self, value ):
		"""
			Returns None if the value would be valid for
			this bone, an error-message otherwise.
		"""
		if value==None:
			return( "No value entered" )

	def serialize( self, valuesCache, name, entity ):
		"""
			Serializes this bone into something we
			can write into the datastore.

			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: String
			:returns: dict
		"""
		if name != "key":
			entity.set( name, valuesCache[name], self.indexed )
		return( entity )

	def unserialize( self, valuesCache, name, expando ):
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.
			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: String
			:param expando: An instance of the dictionary-like db.Entity class
			:type expando: db.Entity
			:returns: bool
		"""
		if name in expando:
			valuesCache[name] = expando[ name ]
		return( True )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter, prefix=None ):
		"""
			Parses the searchfilter a client specified in his Request into
			something understood by the datastore.
			This function must:

				* Ignore all filters not targeting this bone
				* Safely handle malformed data in rawFilter
					(this parameter is directly controlled by the client)

			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:param skel: The :class:`server.db.Query` this bone is part of
			:type skel: :class:`server.skeleton.Skeleton`
			:param dbFilter: The current :class:`server.db.Query` instance the filters should be applied to
			:type dbFilter: :class:`server.db.Query`
			:param rawFilter: The dictionary of filters the client wants to have applied
			:type rawFilter: dict
			:returns: The modified :class:`server.db.Query`
		"""
		def fromShortKey( key ):
			if isinstance(key, basestring ):
				try:
					key = db.Key( encoded=key )
				except:
					key = unicode( key )
					if key.isdigit():
						key = long( key )
					key = db.Key.from_path( skel.kindName, key )
			assert isinstance( key, db.Key )
			return( key )

		if name == "key" and "key" in rawFilter and prefix is None:
			if isinstance( rawFilter["key"], list ):

				keyList = [ fromShortKey( key  ) for key in rawFilter["key"] ]

				if keyList:
					origQuery = dbFilter.datastoreQuery
					kind = dbFilter.getKind()

					try:
						dbFilter.datastoreQuery = db.MultiQuery( [db.DatastoreQuery( dbFilter.getKind(), filters={ db.KEY_SPECIAL_PROPERTY: x } ) for x in keyList ], () )
					except db.BadKeyError: #Invalid key
						raise RuntimeError()
					except UnicodeEncodeError: # Also invalid key
						raise RuntimeError()

							#Monkey-fix for datastore.MultiQuery not setting an kind and therefor breaking order()
					dbFilter.setKind( kind )
					for k, v in origQuery.items():
						dbFilter.filter( k, v )

			else:
				try:
					dbFilter.filter( db.KEY_SPECIAL_PROPERTY, fromShortKey( rawFilter["key"] ) )
				except: #Invalid key or something
					raise RuntimeError()

			return dbFilter

		myKeys = [ key for key in rawFilter.keys() if (key==name or key.startswith( name+"$" )) ]

		if len( myKeys ) == 0:
			return( dbFilter )

		if not self.indexed and name != "key":
			logging.warning( "Invalid searchfilter! %s is not indexed!" % name )
			raise RuntimeError()

		for key in myKeys:
			value = rawFilter[ key ]
			tmpdata = key.partition("$")

			if len( tmpdata ) > 2:
				if isinstance( value, list ):
					continue
				if tmpdata[2]=="lt":
					dbFilter.filter( (prefix or "")+tmpdata[0] + " <" , value )
				elif tmpdata[2]=="gt":
					dbFilter.filter( (prefix or "")+tmpdata[0] + " >",  value )
				elif tmpdata[2]=="lk":
					dbFilter.filter( (prefix or "")+tmpdata[0],  value )
				else:
					dbFilter.filter( (prefix or "")+tmpdata[0],  value )
			else:
				if isinstance( value, list ):
					dbFilter.filter( (prefix or "")+key+" IN", value )
				else:
					dbFilter.filter( (prefix or "")+key, value )

		return dbFilter

	def buildDBSort( self, name, skel, dbFilter, rawFilter ):
		"""
			Same as buildDBFilter, but this time its not about filtering
			the results, but by sorting them.
			Again: rawFilter is controlled by the client, so you *must* expect and safely hande
			malformed data!

			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:param skel: The :class:`server.skeleton.Skeleton` instance this bone is part of
			:type skel: :class:`server.skeleton.Skeleton`
			:param dbFilter: The current :class:`server.db.Query` instance the filters should be applied to
			:type dbFilter: :class:`server.db.Query`
			:param rawFilter: The dictionary of filters the client wants to have applied
			:type rawFilter: dict
			:returns: The modified :class:`server.db.Query`
		"""
		if "orderby" in rawFilter and rawFilter["orderby"] == name:
			if not self.indexed:
				logging.warning( "Invalid ordering! %s is not indexed!" % name )
				raise RuntimeError()
			if "orderdir" in rawFilter and rawFilter["orderdir"]=="1":
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


	def getSearchTags(self, valuesCache, name):
		"""
			Returns a list of Strings which will be included in the
			fulltext-index for this bone.

			.. NOTE::
				This function gets only called, if the ViUR internal
				fulltext-search is used. If you enable the search-API
				by setting a searchIndex on the skeleton, getSearchDocumentFields
				is called instead.

			:return: List of Strings
		"""
		res = []
		if not valuesCache[name]:
			return( res )
		for line in unicode(valuesCache[name]).lower().splitlines():
			for key in line.split(" "):
				key = "".join( [ c for c in key if c.lower() in conf["viur.searchValidChars"] ] )
				if key and key not in res and len(key)>3:
					res.append( key )
		return( res )

	def getSearchDocumentFields(self, valuesCache, name, prefix = ""):
		"""
			Returns a list of search-fields (GAE search API) for this bone.
		"""
		return [search.TextField(name=prefix + name, value=unicode(valuesCache[name]))]

	def getUniquePropertyIndexValue( self, valuesCache, name ):
		"""
			Returns an hash for our current value, used to store in the uniqueProptertyValue index.
		"""
		if valuesCache[name] is None:
			return( None )
		h = hashlib.sha256()
		h.update( unicode( valuesCache[name] ).encode("UTF-8") )
		res = h.hexdigest()
		if isinstance( valuesCache[name], int ) or isinstance( valuesCache[name], float ) or isinstance( valuesCache[name], long ):
			return("I-%s" % res )
		elif isinstance( valuesCache[name], str ) or isinstance( valuesCache[name], unicode ):
			return("S-%s" % res )
		raise NotImplementedError("Type %s can't be safely used in an uniquePropertyIndex" % type(valuesCache[name]) )

	def getReferencedBlobs( self, valuesCache, name ):
		"""
			Returns the list of blob keys referenced from this bone
		"""
		return( [] )

	def performMagic( self, valuesCache, name, isAdd ):
		"""
			This function applies "magically" functionality which f.e. inserts the current Date or the current user.
			@param isAdd: Signals whereever this is an add or edit operation.
			:type isAdd: bool
		"""
		pass #We do nothing by default

	def postSavedHandler( self, valuesCache, boneName, skel, key, dbObj ):
		"""
			Can be overridden to perform further actions after the main entity has been written.

			:param boneName: Name of this bone
			:type boneName: String

			:param skel: The skeleton this bone belongs to
			:type skel: Skeleton

			:param key: The (new?) Database Key we've written to
			:type key: str

			:param dbObj: The db.Entity object written
			:type dbObj: db.Entity
		"""
		pass

	def postDeletedHandler(self, skel, boneName, key):
		"""
			Can be overridden to perform  further actions after the main entity has been deleted.

			:param skel: The skeleton this bone belongs to
			:type skel: Skeleton
			:param boneName: Name of this bone
			:type boneName: String
			:param key: The old Database Key of hte entity we've deleted
			:type id: String
		"""
		pass

	def refresh(self, valuesCache, boneName, skel):
		"""
			Refresh all values we might have cached from other entities.
		"""
		pass

	def mergeFrom(self, valuesCache, boneName, otherSkel):
		"""
			Clones the values from other into this instance
		"""
		if getattr(otherSkel, boneName) is None:
			return
		if not isinstance(getattr(otherSkel, boneName), type(self)):
			logging.error("Ignoring values from conflicting boneType (%s is not a instance of %s)!" % (getattr(otherSkel, boneName), type(self)))
			return
		valuesCache[boneName] = copy.deepcopy(otherSkel.valuesCache.get(boneName, None))

	def setBoneValue(self, valuesCache, boneName, value, append, *args, **kwargs):
		"""
			Set our value to 'value'.
			Santy-Checks are performed; if the value is invalid, we flip our value back to its original
			(default) value and return false.

			:param valuesCache: Dictionary with the current values from the skeleton we belong to
			:type valuesCache: dict
			:param boneName: The Bone which should be modified
			:type boneName: str
			:param value: The value that should be assigned. It's type depends on the type of that bone
			:type boneName: object
			:param append: If true, the given value is appended to the values of that bone instead of
				replacing it. Only supported on bones with multiple=True
			:type append: bool
			:return: Wherever that operation succeeded or not.
			:rtype: bool

		"""
		if append:
			raise ValueError("append is not possible on %s bones" % self.type)
		res = self.fromClient(valuesCache, boneName, {boneName: value})
		if not res:
			return True
		else:
			return False
