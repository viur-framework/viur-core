# -*- coding: utf-8 -*-
import copy
from server.bones import baseBone,  dateBone
from collections import OrderedDict
from threading import local
from google.appengine.ext import ndb
from server.utils import generateExpandoClass
from time import time
from google.appengine.api import search
from server.config import conf
from server.bones import selectOneBone, baseBone
from server.tasks import CallableTask, CallableTaskBase
from google.appengine.api import datastore, datastore_types, datastore_errors
from google.appengine.api import memcache
from google.appengine.api import search
from copy import deepcopy
import logging

class BoneCounter(local):
	def __init__(self):
		self.count = 0

_boneCounter = BoneCounter()

class Query( object ):
	def __init__(self, skelClass):
		super( Query, self ).__init__()
		self.skelClass = skelClass
		self.kind = skelClass().entityName
		self.limit = 30
		self.startCursor = None
		self.endCursor = None
		self.filters = {}
		self.orders = []
	
	def toDatastoreQuery(self, keysOnly=False):
		dbFilter = datastore.Query(kind=self.kind, keys_only=keysOnly)
		skel = self.skelClass()
		bones = [ getattr( skel, key ) for key in dir( skel ) if not "__" in key and isinstance( getattr( skel, key ) , baseBone ) ]
		try:
			#First, filter non-relational bones
			for bone in [ x for x in bones if not isinstance( x, relationalBone ) ]:
				dbFilter = bone.buildDBFilter( key, skel, dbFilter, self.filters )
			#Second, process orderings of non-relational bones
			for bone in [ x for x in bones if not isinstance( x, relationalBone ) ]:
				dbFilter = bone.buildDBSort( key, skel, dbFilter, self.filters )
			#Now filter relational bones
			for bone in [ x for x in bones if isinstance( x, relationalBone ) ]:
				dbFilter = bone.buildDBFilter( key, skel, dbFilter, self.filters )
			#finally process orderings of nelational bones
			for bone in [ x for x in bones if isinstance( x, relationalBone ) ]:
				dbFilter = bone.buildDBSort( key, skel, dbFilter, self.filters )
		except RuntimeError:
			return( None )
		if "search" in self.filters.keys():
			if isinstance( self.filters["search"], list ):
				taglist = [ "".join([y for y in unicode(x).lower() if y in conf["viur.searchValidChars"] ] ) for x in self.filters["search"] ]
			else:
				taglist = [ "".join([y for y in unicode(x).lower() if y in conf["viur.searchValidChars"] ]) for x in unicode(self.filters["search"]).split(" ")] 
			assert not isinstance( dbFilter, datastore.MultiQuery )
			origFilter = dbFilter
			queries = []
			for tag in taglist:
				q = datastore.Query( kind=origFilter.kind() )
				q[ "viur_tags" ] = tag
				queries.append( q )
			for k, v in origFilter.items():
				dbFilter[ k ] = v
		#if "cursor" in rawFilter.keys() and rawFilter["cursor"] and rawFilter["cursor"].lower()!="none":
		#	cursor = ndb.Cursor( urlsafe=rawFilter["cursor"] )
		#if "amount" in list(rawFilter.keys()) and str(rawFilter["amount"]).isdigit() and int( rawFilter["amount"] ) >0 and int( rawFilter["amount"] ) <= 50:
		#	limit = int(rawFilter["amount"])
		#if "postProcessSearchFilter" in dir( skel ):
		#	dbFilter = skel.postProcessSearchFilter( dbFilter, rawFilter )
		#if not dbFilter.orders: #And another NDB fix
		#	dbFilter = dbFilter.order( skel._expando._key )
		return( dbFilter )
	
	def filter( self, key, value=None ):
		if isinstance( key, dict ):
			self.filters.update( **key )
		elif key and value!=None:
			self.filters[ key ] = value
		else:
			assert False
	
	def fetch(self):
		skel = self.skelClass()
		if skel.searchIndex and "search" in rawFilter.keys(): #We perform a Search via Google API - all other parameters are ignored
			searchRes = search.Index( name=skel.searchIndex ).search( query=search.Query( query_string=rawFilter["search"], options=search.QueryOptions( limit=25 ) ) )
			tmpRes = [ ndb.Key(urlsafe=x.doc_id[ 2: ] ) for x in searchRes ]
			if tmpRes: #Again.. Workaround for broken ndb API: Filtering IN using an empty list: exception instead of empty result
				res = dbFilter.filter(  generateExpandoClass( dbFilter.kind )._key.IN( tmpRes ) )
			else:
				res = dbFilter.filter(  ndb.GenericProperty("_-Non-ExIstIng_-Property_-" ) == None )
			res = res.order( skel._expando._key )
			res.limit = limit
			res.cursor = None
			return( res )
#
		q = self.toDatastoreQuery( keysOnly=True )
		if not q: #Invalid search-filter
			return( Skellist( self.skelClass ) )
		tmpList = list( q.Run() )
		if not tmpList:
			return( Skellist( self.skelClass ) )
		logging.error( [ type(x) for x in tmpList ] )
		if isinstance( tmpList[0], datastore_types.Key ): #Key-Only query
			keyList = [ str(x) for x in tmpList ]
			resultList = Skellist( self.skelClass )
			while keyList: #Fetch in Batches of 30 entries, as the max size for bulk_get is limited to 32MB
				currentBatch = keyList[ : 30]
				keyList = keyList[ 30: ]
				memcacheRes = memcache.get_multi( currentBatch, key_prefix="viur-db-cache:")
				for k in currentBatch:
					skel = self.skelClass()
					if k in memcacheRes.keys() and memcacheRes[ k ]:
						skel.setValues( memcacheRes[ k ] )
					else:
						skel.fromDB( k )
					resultList.append( skel )
		for r in q.Run():
			logging.error( r )
		return( resultList )
	

class Skeleton( object ):
	""" 
		Container-object which holds informations about one entity.
		It must be subclassed where informations about the entityName and its
		attributes (Bones) are specified.
		
		Its an hacked Object that stores it members in a OrderedDict-Instance so the Order stays constant
	"""
	def __setattr__(self, key, value):
		if not "__dataDict__" in dir( self ):
			super( Skeleton, self ).__setattr__( "__dataDict__", OrderedDict() )
		if not "__" in key and isinstance( value , baseBone ):
			self.__dataDict__[ key ] =  value 
		super( Skeleton, self ).__setattr__( key, value )

	def __delattr__(self, key):
		if( key in dir( self ) ):
			super( Skeleton, self ).__delattr__( key )
		else:
			del self.__dataDict__[key]


	
	def items(self):
		return( self.__dataDict__.items() )
	
	entityName = ""
	searchIndex = None

	id = baseBone( readOnly=True, visible=False, descr="ID")
	creationdate = dateBone( readOnly=True, visible=False, creationMagic=True, searchable=True, descr="created at" )
	changedate = dateBone( readOnly=True, visible=False, updateMagic=True, searchable=True, descr="updated at" )

	def __init__( self, entityName=None, *args,  **kwargs ):
		"""Create a local copy from the global Skel-class."""
		super(Skeleton, self).__init__(*args, **kwargs)
		self.entityName = entityName or self.entityName
		self._rawValues = {}
		self._pendingResult = None
		self.errors = {}
		tmpList = []
		self.__dataDict__ = OrderedDict()
		for key in dir(self):
			bone = getattr( self, key )
			if not "__" in key and isinstance( bone , baseBone ):
				tmpList.append( (key, bone) )
		tmpList.sort( key=lambda x: x[1].idx )
		for key, bone in tmpList:
			bone = copy.copy( bone )
			setattr( self, key, bone )

	def __setitem__(self, name, value):
		self.checkPending()
		self._rawValues[ name ] = value
	
	def __getitem__(self, name ):
		self.checkPending()
		return( self._rawValues[ name ] )

	def all(self):
		return( Query( type( self ) ) )

	def fromDB( self,  id, defer=False ):
		"""
			Populates the current instance with values read from the given DB-Key.
			Its current (maybe unsaved data) is discarded.
			
			@param id: An DB.Key or a DB.Query from which the data is read.
			@type id: DB.Key, String or DB.Query
			@returns: True on success; False if the key could not be found
		"""
		logging.error("fromDB")
		if isinstance(id, basestring ):
			try:
				id = datastore_types.Key( encoded=id )
			except datastore_errors.BadKeyError:
				id = unicode( id )
				if id.isdigit:
					id = long( id )
				id = datastore_types.Key.from_path( self.entityName, id )
		assert isinstance( id, datastore_types.Key )
		self._pendingResult = datastore.GetAsync( id )
		if not defer:
			self.checkPending()
		logging.error("FromDB  %s" % str( self ))
		"""		
				if isinstance( id, ndb.Query ):
					res = id.get()
				else:
					try:
						res = ndb.Key(urlsafe=id).get()
					except:
						return( False )
		"""

	def checkPending(self):
		logging.error( "ChekPending %s" % str( self ) )
		if self._pendingResult==None:
			return
		logging.error("Yes")
		try:
			res = self._pendingResult.get_result()
			self._pendingResult = None
		except:
			logging.warning("Got stale result!")
			return
		self.setValues( res )
		id = str( res.key() )
		for key in dir( self ):
			bone = getattr( self, key )
			if not "__" in key and isinstance( bone , baseBone ):
				if "postUnserialize" in dir( bone ):
					bone.postUnserialize( key, self, id )

	
	def toDB( self, id=False, clearUpdateTag=False ):
		"""
			Saves the current data of this instance into the database.
			If an ID is specified, this entity is updated, otherwise an new
			Entity is created.
			
			@param id: DB-Key to update. If none, a new one will be created
			@type id: string or None
			@param clearUpdateTag: If true, this entity wont be marked dirty; so the background-task updating releations wont catch this one. Default: False
			@type clearUpdateTag: Bool
			@returns String DB-Key
		"""
		def txnUpdate( id, dbfields ):
			dbObj = ndb.Key( urlsafe=id ).get()
			if not dbObj:
				dbObj = self._expando( key=ndb.Key( urlsafe=id ), **dbfields )
			for k,v in dbfields.items():
				setattr( dbObj, k, v )
			dbObj.put()
		dbfields = {}
		tags = []
		for key in dir( self ):
			if "__" not in key:
				_bone = getattr( self, key )
				if( isinstance( _bone, baseBone )  ):
					data = _bone.serialize( key ) 
					dbfields.update( data )
					if _bone.searchable:
						tags += [ tag for tag in _bone.getTags() if (tag not in tags and len(tag)<400) ]
		if tags:
			dbfields["viur_tags"] = tags
		if clearUpdateTag:
			dbfields["viur_delayed_update_tag"] = 0 #Mark this entity as Up-to-date.
		else:
			dbfields["viur_delayed_update_tag"] = time() #Mark this entity as dirty, so the background-task will catch it up and update its references.
		if "preProcessSerializedData" in dir( self ):
			dbfields = self.preProcessSerializedData( dbfields )
		if id:
			ndb.transaction( lambda: txnUpdate( id, dbfields ) )
		else:
			dbObj = datastore.Entity( self.entityName )
			for k, v in dbfields.items():
				dbObj[ k ] = v
			dbObj.set_unindexed_properties( [ x for x in dir( self ) if (isinstance( getattr( self, x ), baseBone ) and not getattr( self, x ).searchable) ] )
			id = str( datastore.Put( dbObj ) )
		if self.searchIndex: #Add a Document to the index if specified
			fields = []
			for key in dir( self ):
				if "__" not in key:
					_bone = getattr( self, key )
					if( isinstance( _bone, baseBone )  ) and _bone.searchable:
						fields.extend( _bone.getSearchDocumentFields(key ) )
			if fields:
				try:
					doc = search.Document(doc_id="s_"+str(id), fields= fields )
					search.Index(name=self.searchIndex).add( doc )
				except:
					pass
		for key in dir( self ):
			if "__" not in key:
				_bone = getattr( self, key )
				if( isinstance( _bone, baseBone )  ) and "postSavedHandler" in dir( _bone ):
					_bone.postSavedHandler( key, self, id, dbfields )
		if "postProcessSerializedData" in dir( self ):
			self.postProcessSerializedData( id,  dbfields )
		return( id )
			
	def delete( self, id ):
		"""
			Deletes the specified entity from the database.
			
			@param id: DB.Key to delete
			@type id: String 
		"""
		ndb.Key( urlsafe=id ).delete()
		for key in dir( self ):
			if "__" not in key:
				_bone = getattr( self, key )
				if( isinstance( _bone, baseBone )  ) and "postDeletedHandler" in dir( _bone ):
					_bone.postDeletedHandler( self, key, id )
		if self.searchindex:
			try:
				search.Index( name=self.searchindex ).remove( "s_"+str(id) )
			except:
				pass

	def setValues( self, values ):
		"""
			Update the values of the current instance with the ones from the given dictionary.
			Warning: Performs no error-checking for invalid values! Its possible to set invalid values
			which may break the serialize/deserialize function of the related bone!
			If no bone could be found for a given key-name. this key is ignored.
			Values of other bones, not mentioned in this dict are also left unchanged.
			
			@param values: Dictionary with new Values.
			@type values: Dict
		"""
		for key in dir( self ):
			if not "__" in key:
				_bone = getattr( self, key )
				if isinstance( _bone, baseBone ):
					if key=="id":
						_bone.value = str( values.key() )
					else:
						_bone.unserialize( key, values )
		self._rawValues.update( values )
		
	
	def getValues(self):
		"""
			Returns the current values as dictionary
			
			@returns: dict
		"""
		res = {}
		for key in dir( self ):
			if not "__" in key:
				_bone = getattr( self, key )
				if isinstance( _bone, baseBone ):
					res[ key ] = _bone.value
		return( res )

	def fromClient( self, data ):
		"""
			Reads the data supplied by data.
			Unlike setValues, error-checking is performed.
			The values might be in a different representation than the one used in getValues/serValues.
			Even if this function returns False, all bones are guranteed to be in a valid state:
			The ones which have been read correctly contain their data; the other ones are set back to a safe default (None in most cases)
			So its possible to call save() afterwards even if reading data fromClient faild (through this might violates the assumed consitency-model!).
			
			@param data: Dictionary from which the data is read
			@type data: Dict
			@returns: True if the data was successfully read; False otherwise (eg. some required fields where missing or invalid)
		"""
		complete = True
		self.errors = {}
		for key in dir( self ):
			if "__" not in key:
				_bone = getattr( self, key )
				if( isinstance( _bone, baseBone ) ):
					if _bone.readOnly:
						continue
					if key in data:
						error = _bone.fromClient( data[ key ] )
						self.errors[ key ] = error
						if error  and _bone.required:
							complete = False
							
					else:
						error = _bone.fromClient( None ) 
						self.errors[ key ] = error
						if _bone.required:
							complete = False
		if( len( data )==0 or (len(data)==1 and "id" in data) or ("nomissing" in data.keys() and str(data["nomissing"])=="1") ):
			self.errors = {}
		return( complete )
	
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


### Tasks ###

@CallableTask
class TaskUpdateSeachIndex( CallableTaskBase ):
	"""This tasks loads and saves *every* entity of the given modul.
	This ensures an updated searchindex and verifies consistency of this data.
	"""
	id = "rebuildsearchindex"
	name = u"Rebuild a Searchindex"
	descr = u"Needs to be called whenever a search-releated parameters are changed."
	direct = False
	
	def dataSkel(self):
		modules = []
		for modulName in dir( conf["viur.mainApp"] ):
			modul = getattr( conf["viur.mainApp"], modulName )
			if "editSkel" in dir( modul ) and not modulName in modules:
				modules.append( modulName )
		skel = Skeleton( self.entityName )
		skel.modul = selectOneBone( descr="Modul", values={ x: x for x in modules}, required=True )
		return( skel )

	def execute( self, modul=None, *args, **kwargs ):
		Skel = None
		if modul in dir( conf["viur.mainApp"] ):
			if "editSkel" in dir( getattr( conf["viur.mainApp"], modul ) ):
				Skel = getattr( conf["viur.mainApp"], modul ).editSkel
		if not Skel:
			logging.error("TaskUpdateSeachIndex: Invalid modul")
			return
		subscriptionClass = generateExpandoClass( Skel.entityName )
		for sub in subscriptionClass.query().iter():
			try:
				skel = Skel()
				skel.fromDB( str(sub.key.urlsafe()) )
				skel.toDB( str(sub.key.urlsafe()) )
			except Exception as e:
				logging.error("Updating %s failed" % str(sub.key.urlsafe()) )
				logging.error( e )
