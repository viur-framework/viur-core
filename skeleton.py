# -*- coding: utf-8 -*-
import copy
from server.bones import baseBone,  dateBone
from collections import OrderedDict
from threading import local
from server import db
from time import time
from google.appengine.api import search
from server.config import conf
from server.bones import selectOneBone, baseBone, relationalBone
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

class Skeleton( object ):
	""" 
		Container-object which holds informations about one entity.
		It must be subclassed where informations about the kindName and its
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
	
	kindName = ""
	searchIndex = None

	id = baseBone( readOnly=True, visible=False, descr="ID")
	creationdate = dateBone( readOnly=True, visible=False, creationMagic=True, indexed=True, descr="created at" )
	changedate = dateBone( readOnly=True, visible=False, updateMagic=True, indexed=True, descr="updated at" )

	def __init__( self, kindName=None, *args,  **kwargs ):
		"""
			Create a local copy from the global Skel-class.
			
			@param kindName: If set, override the entity kind were operating on.
			@type kindName: String or None
		"""
		super(Skeleton, self).__init__(*args, **kwargs)
		self.kindName = kindName or self.kindName
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
		"""
			Returns a db.Query object bound to this skeleton.
			This query will operate on our kindName, and its valid
			to use its special methods mergeExternalFilter and getSkel.
		"""
		return( db.Query( self.kindName, srcSkelClass=type( self ) ) )
	
	def fromDB( self,  id ):
		"""
			Populates the current instance with values read from the given DB-Key.
			Its current (maybe unsaved data) is discarded.
			
			@param id: An DB.Key or a DB.Query from which the data is read.
			@type id: DB.Key, String or DB.Query
			@returns: True on success; False if the key could not be found
		"""
		if isinstance(id, basestring ):
			try:
				id = datastore_types.Key( id )
			except datastore_errors.BadKeyError:
				id = unicode( id )
				if id.isdigit():
					id = long( id )
				id = datastore_types.Key.from_path( self.kindName, id )
		assert isinstance( id, datastore_types.Key )
		try:
			dbRes = datastore.Get( id )
		except db.EntityNotFoundError:
			return( False )
		if dbRes is None:
			return( False )
		self.setValues( dbRes )
		id = str( dbRes.key() )
		for key in dir( self ):
			bone = getattr( self, key )
			if not "__" in key and isinstance( bone , baseBone ):
				if "postUnserialize" in dir( bone ):
					bone.postUnserialize( key, self, id )
		return( True )

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
		def txnUpdate( id, dbfields, unindexedProperties ):
			try:
				dbObj = db.Get( db.Key( id ) )
			except db.EntityNotFoundError:
				k = db.Key( id )
				dbObj = db.Entity( k.kind(), id=k.id(), name=k.name() )
			for k,v in dbfields.items():
				dbObj[ k ] =  v
			dbObj.set_unindexed_properties( unindexedProperties )
			db.Put( dbObj )
		dbfields = {}
		tags = []
		for key in dir( self ):
			if "__" not in key:
				_bone = getattr( self, key )
				if( isinstance( _bone, baseBone )  ):
					data = _bone.serialize( key ) 
					dbfields.update( data )
					if _bone.indexed:
						tags += [ tag for tag in _bone.getTags() if (tag not in tags and len(tag)<400) ]
		if tags:
			dbfields["viur_tags"] = tags
		if clearUpdateTag:
			dbfields["viur_delayed_update_tag"] = 0 #Mark this entity as Up-to-date.
		else:
			dbfields["viur_delayed_update_tag"] = time() #Mark this entity as dirty, so the background-task will catch it up and update its references.
		if "preProcessSerializedData" in dir( self ):
			dbfields = self.preProcessSerializedData( dbfields )
		unindexedProperties = [ x for x in dir( self ) if (isinstance( getattr( self, x ), baseBone ) and not getattr( self, x ).indexed) ]
		if id:
			db.RunInTransaction( txnUpdate, id, dbfields, unindexedProperties )
		else:
			dbObj = datastore.Entity( self.kindName )
			for k, v in dbfields.items():
				dbObj[ k ] = v
			dbObj.set_unindexed_properties( unindexedProperties )
			id = str( datastore.Put( dbObj ) )
		if self.searchIndex: #Add a Document to the index if specified
			fields = []
			for key in dir( self ):
				if "__" not in key:
					_bone = getattr( self, key )
					if( isinstance( _bone, baseBone )  ) and _bone.indexed:
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
		db.Delete( db.Key( id ) )
		for key in dir( self ):
			if "__" not in key:
				_bone = getattr( self, key )
				if( isinstance( _bone, baseBone )  ) and "postDeletedHandler" in dir( _bone ):
					_bone.postDeletedHandler( self, key, id )
		if self.searchIndex:
			try:
				search.Index( name=self.searchIndex ).remove( "s_"+str(id) )
			except:
				pass

	def setValues( self, values ):
		"""
			Update the values of the current instance with the ones from the given dictionary.
			Usually used to merge values fetched from the database into the current skeleton instance.
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
			Returns the current values as dictionary.
			This is *not* the inverse of setValues as its not
			valid to save these values into the database yourself!
			Doing so will result in an entity that might not appear
			in searches and possibly break the deserializion of the whole
			list if it does.
			
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
	
class Skellist( list ):
	"""
		Class to hold multiple skeletons along
		other commonly used informations (cursors, etc)
		of that result set.
		
		Usually created by calling skel.all(). ... .fetch()
	"""

	def __init__( self, viewSkel, queryRes=None ):
		"""
			@param viewSkel: The baseclass for all entries in this list
			@type viewSkel: Class
			@queryRes: An db.Query object. If set, this instance will fill itself the results of that query.
						*Warning*: You *must* ensure that the amount of results that query will yield is limited"
			@type queryRes: db.Query
		"""
		super( Skellist, self ).__init__()
		self.viewSkel = viewSkel
		self.cursor = None
		self.hasMore = False
		self.cacheRes = None
		self.future = None
		self.keyList = None
		if queryRes!=None:
			self.keyList = list( queryRes )
			if not self.keyList:
				return
			if isinstance( self.keyList[0], datastore_types.Key ): #Key-Only query
				#Check Memcache first
				self.cacheRes = {}
				keyList = [ str(x) for x in self.keyList ]
				while keyList: #Fetch in Batches of 30 entries, as the max size for bulk_get is limited to 32MB
					currentBatch = keyList[ : 30]
					keyList = keyList[ 30: ]
					self.cacheRes.update( memcache.get_multi( currentBatch, key_prefix="viur-db-cache:") )
				#Fetch the rest from DB
				missigKeys = [ x for x in self.keyList if not str(x) in self.cacheRes.keys() ]
				self.future = datastore.GetAsync( missigKeys )
			else: #We got a full result set
				for entry in self.keyList:
					s = self.viewSkel()
					s.setValues( entry )
					self.append( s )
				self.keyList = None

	def mergeFuture(self):
		"""
			Ensures, that this instance is in a valid state if its accessed
			(i.e. all requests made in the background have finished and merged)
		"""
		if self.future==None:
			return
		dbResults = list( self.future.get_result() )
		for key in [ str( x ) for x in self.keyList ]:
			skel = self.viewSkel()
			if key in self.cacheRes.keys():
				skel.setValues( self.cacheRes[ key ] )
			else:
				entity = None
				for e in dbResults:
					if str( e.key() ) == key:
						entity = e
						break
				if not entity:
					logging.warning("Ive missed an entry: %s" % key )
				else:
					skel.setValues( entity )
			self.append( skel )
		self.future = None
		self.cacheRes = None
		self.keyList = None
	
	def __contains__( self, *args, **kwargs ):
		self.mergeFuture()
		return( super( Skellist, self ).__contains__( *args, **kwargs ) )

	def __delitem__( self, *args, **kwargs ):
		self.mergeFuture()
		return( super( Skellist, self ).__delitem__( *args, **kwargs ) )

	def __getitem__( self, *args, **kwargs ):
		self.mergeFuture()
		return( super( Skellist, self ).__getitem__( *args, **kwargs ) )

	def __iter__( self, *args, **kwargs ):
		self.mergeFuture()
		return( super( Skellist, self ).__iter__( *args, **kwargs ) )

	def __len__( self, *args, **kwargs ):
		self.mergeFuture()
		return( super( Skellist, self ).__len__( *args, **kwargs ) )

	def count( self, *args, **kwargs ):
		self.mergeFuture()
		return( super( Skellist, self ).count( *args, **kwargs ) )

	def index( self, *args, **kwargs ):
		self.mergeFuture()
		return( super( Skellist, self ).index( *args, **kwargs ) )

	def reverse( self, *args, **kwargs ):
		self.mergeFuture()
		return( super( Skellist, self ).reverse( *args, **kwargs ) )
		
	def sort( self, *args, **kwargs ):
		self.mergeFuture()
		return( super( Skellist, self ).sort( *args, **kwargs ) )


### Tasks ###

@CallableTask
class TaskUpdateSeachIndex( CallableTaskBase ):
	"""This tasks loads and saves *every* entity of the given modul.
	This ensures an updated searchIndex and verifies consistency of this data.
	"""
	id = "rebuildsearchIndex"
	name = u"Rebuild a Searchindex"
	descr = u"Needs to be called whenever a search-releated parameters are changed."
	direct = False
	
	def dataSkel(self):
		modules = []
		for modulName in dir( conf["viur.mainApp"] ):
			modul = getattr( conf["viur.mainApp"], modulName )
			if "editSkel" in dir( modul ) and not modulName in modules:
				modules.append( modulName )
		skel = Skeleton( self.kindName )
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
		subscriptionClass = generateExpandoClass( Skel.kindName )
		for sub in subscriptionClass.query().iter():
			try:
				skel = Skel()
				skel.fromDB( str(sub.key.urlsafe()) )
				skel.toDB( str(sub.key.urlsafe()) )
			except Exception as e:
				logging.error("Updating %s failed" % str(sub.key.urlsafe()) )
				logging.error( e )
