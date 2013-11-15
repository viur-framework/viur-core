# -*- coding: utf-8 -*-
import copy
from server.bones import baseBone, dateBone, selectOneBone, relationalBone, stringBone
from collections import OrderedDict
from threading import local
from server import db
from time import time
from google.appengine.api import search
from server.config import conf
from server import utils
from server.tasks import CallableTask, CallableTaskBase, callDeferred
import inspect, os
import logging

class BoneCounter(local):
	def __init__(self):
		self.count = 0

_boneCounter = BoneCounter()

class MetaSkel( type ):
	_skelCache = {}
	__reservedKeywords_ = [ "self", "cursor", "amount", "orderby", "orderdir", "style" ]
	def __init__( cls, name, bases, dct ):
		kindName = cls.kindName
		#if kindName in MetaSkel._skelCache.keys():
		#	raise NotImplementedError("Duplicate definition of %s" % kindName)
		relFileName = inspect.getfile(cls).replace( os.getcwd(),"" )
		if not relFileName.strip(os.path.sep).startswith("models") and not relFileName.strip(os.path.sep).startswith("server"): # and any( [isinstance(x,baseBone) for x in [ getattr(cls,y) for y in dir( cls ) if not y.startswith("_") ] ] ):
			raise NotImplementedError("Skeletons must be defined in /models/")
		if kindName:
			MetaSkel._skelCache[ kindName ] = cls
		for key in dir( cls ):
			if isinstance( getattr( cls, key ), baseBone ):
				if key.lower()!=key:
					raise AttributeError( "Bonekeys must be lowercase" )
				if "." in key:
					raise AttributeError( "Bonekeys cannot not contain a dot (.) - got %s" % key )
				if key in MetaSkel.__reservedKeywords_:
					raise AttributeError( "Your bone cannot have any of the following keys: %s" % str( MetaSkel.__reservedKeywords_ ) )
		return( super( MetaSkel, cls ).__init__( name, bases, dct ) )

def skeletonByKind( kindName ):
	if conf["viur.models"] is None:
		raise NotImplementedError("You must call server.setup before you can access the skeletons!")
	if not kindName:
		return( None )
	assert kindName in MetaSkel._skelCache
	return MetaSkel._skelCache[ kindName ]

class Skeleton( object ):
	""" 
		Container-object which holds informations about one entity.
		It must be subclassed where informations about the kindName and its
		attributes (Bones) are specified.
		
		Its an hacked Object that stores it members in a OrderedDict-Instance so the Order stays constant
	"""
	__metaclass__ = MetaSkel

	def __setattr__(self, key, value):
		if not "__dataDict__" in dir( self ):
			super( Skeleton, self ).__setattr__( "__dataDict__", OrderedDict() )
		if not "__" in key:
			if isinstance( value , baseBone ):
				self.__dataDict__[ key ] =  value
			elif key in self.__dataDict__.keys(): #Allow setting a bone to None again
				self.__dataDict__[ key ] =  value
		super( Skeleton, self ).__setattr__( key, value )

	def __delattr__(self, key):
		if( key in dir( self ) ):
			super( Skeleton, self ).__delattr__( key )
		else:
			del self.__dataDict__[key]

	def items(self):
		return( self.__dataDict__.items() )

	kindName = "" # To which kind we save our data to
	searchIndex = None # If set, use this name as the index-name for the GAE search API
	enforceUniqueValuesFor = None # If set, enforce that the values of that bone are unique.
	subSkels = {} # List of pre-defined sub-skeletons of this type
	isBaseClassSkel = False # If True, this skeleton won't be handled by tasks like the relational update task

	id = baseBone( readOnly=True, visible=False, descr="ID")
	creationdate = dateBone( readOnly=True, visible=False, creationMagic=True, indexed=True, descr="created at" )
	changedate = dateBone( readOnly=True, visible=False, updateMagic=True, indexed=True, descr="updated at" )

	@classmethod
	def subSkel(cls, name):
		skel = cls()
		if not name in skel.subSkels.keys():
			raise ValueError("Unknown sub-skeleton %s for skel %s" % (name, skel.kindName))
		boneList = skel.subSkels[name]
		for key in dir(skel):
			if key.startswith("_"):
				continue
			bone = getattr( skel, key )
			if not isinstance(bone, baseBone):
				continue
			keepBone = key in boneList
			if not keepBone: #Test if theres a prefix-match that allows it
				for boneKey in boneList:
					if boneKey.endswith("*") and key.startswith(boneKey[: -1]):
						keepBone = True
						break
			if not keepBone: #Remove that bone from the skeleton
				setattr(skel,key,None)
		return( skel )


	def __init__( self, kindName=None, *args,  **kwargs ):
		"""
			Create a local copy from the global Skel-class.
			
			@param kindName: If set, override the entity kind were operating on.
			@type kindName: String or None
		"""
		super(Skeleton, self).__init__(*args, **kwargs)
		self.kindName = kindName or self.kindName
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
		if self.enforceUniqueValuesFor:
			uniqueProperty = (self.enforceUniqueValuesFor[0] if isinstance( self.enforceUniqueValuesFor, tuple ) else self.enforceUniqueValuesFor)
			if not uniqueProperty in [ key for (key,bone) in tmpList ]:
				raise( ValueError("Cant enforce unique variables for unknown bone %s" % uniqueProperty ) )

	def __setitem__(self, name, value):
		try:
			bone = getattr( self, name )
		except:
			bone = None
		if not isinstance( bone, baseBone ):
			raise KeyError("%s is no valid Bone!" % name )
		bone.value = value

	def __getitem__(self, name ):
		try:
			bone = getattr( self, name )
		except:
			bone = None
		if not isinstance( bone, baseBone ):
			raise KeyError("%s is no valid Bone!" % name )
		return( bone.value )

	def all(self):
		"""
			Returns a db.Query object bound to this skeleton.
			This query will operate on our kindName, and its valid
			to use its special methods mergeExternalFilter and getSkel.
		"""
		return( db.Query( self.kindName, srcSkelClass=type( self ) ) )

	def fromDB( self, id ):
		"""
			Populates the current instance with values read from the given DB-Key.
			Its current (maybe unsaved data) is discarded.
			
			@param id: An DB.Key or a DB.Query from which the data is read.
			@type id: DB.Key, String or DB.Query
			@returns: True on success; False if the key could not be found
		"""
		if isinstance(id, basestring ):
			try:
				id = db.Key( id )
			except db.BadKeyError:
				id = unicode( id )
				if id.isdigit():
					id = long( id )
				id = db.Key.from_path( self.kindName, id )
		if not isinstance( id, db.Key ):
			raise ValueError("fromDB expects an db.Key instance, an string-encoded key or a long as argument, got \"%s\" instead" % id )
		try:
			dbRes = db.Get( id )
		except db.EntityNotFoundError:
			return( False )
		if dbRes is None:
			return( False )
		if dbRes.kind() != self.kindName:
			# Wrong Kind
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
		def txnUpdate( id, skel, clearUpdateTag ):
			if not id:
				dbObj = db.Entity( skel.kindName )
			else:
				try:
					dbObj = db.Get( db.Key( id ) )
				except db.EntityNotFoundError:
					k = db.Key( id )
					dbObj = db.Entity( k.kind(), id=k.id(), name=k.name(), parent=k.parent() )
			if self.enforceUniqueValuesFor:
				uniqueProperty = (self.enforceUniqueValuesFor[0] if isinstance( self.enforceUniqueValuesFor, tuple ) else self.enforceUniqueValuesFor)
				if "%s.uniqueIndexValue" % uniqueProperty in dbObj.keys():
					oldUniquePropertyValue = dbObj[ "%s.uniqueIndexValue" % uniqueProperty ]
				else:
					oldUniquePropertyValue = None
			unindexed_properties = []
			for key in dir( skel ):
				if "__" not in key:
					_bone = getattr( skel, key )
					if( isinstance( _bone, baseBone )  ):
						tmpKeys = dbObj.keys()
						dbObj = _bone.serialize( key, dbObj )
						newKeys = [ x for x in dbObj.keys() if not x in tmpKeys ] #These are the ones that the bone added
						if not _bone.indexed:
							unindexed_properties += newKeys
						#if _bone.searchable and not skel.searchIndex:
						#	tags += [ tag for tag in _bone.getSearchTags() if (tag not in tags and len(tag)<400) ]
			#if tags:
			#	dbObj["viur_tags"] = tags
			if clearUpdateTag:
				dbObj["viur_delayed_update_tag"] = 0 #Mark this entity as Up-to-date.
			else:
				dbObj["viur_delayed_update_tag"] = time() #Mark this entity as dirty, so the background-task will catch it up and update its references.
			dbObj.set_unindexed_properties( unindexed_properties )
			if "preProcessSerializedData" in dir( self ):
				dbObj = self.preProcessSerializedData( dbObj )
			if self.enforceUniqueValuesFor:
				uniqueProperty = (self.enforceUniqueValuesFor[0] if isinstance( self.enforceUniqueValuesFor, tuple ) else self.enforceUniqueValuesFor)
				# Check if the property is really unique
				newVal = getattr( self, uniqueProperty ).getUniquePropertyIndexValue()
				if newVal is not None:
					try:
						lockObj = db.Get( db.Key.from_path( "%s_uniquePropertyIndex" % self.kindName, newVal ) )
						try:
							ourKey = str( dbObj.key() )
						except: #Its not an update but an insert, no key yet
							ourKey = None
						if lockObj["references"] != ourKey: #This value has been claimed, and that not by us
							raise ValueError("The value of property %s has been recently claimed!" % uniqueProperty )
					except db.EntityNotFoundError: #No lockObj found for that value, we can use that
						pass
					dbObj[ "%s.uniqueIndexValue" % uniqueProperty ] = newVal
				else:
					if "%s.uniqueIndexValue" % uniqueProperty in dbObj.keys():
						del dbObj[ "%s.uniqueIndexValue" % uniqueProperty ]
			if not skel.searchIndex:
				# We generate the searchindex using the full skel, not this (maybe incomplete one)
				tags = []
				for key in dir( self ):
					if "__" not in key:
						_bone = getattr( self, key )
						if( isinstance( _bone, baseBone )  ):
							if _bone.searchable:
								tags += [ tag for tag in _bone.getSearchTags() if (tag not in tags and len(tag)<400) ]
				dbObj["viur_tags"] = tags
			db.Put( dbObj )
			if self.enforceUniqueValuesFor:
				# Now update/create/delte the lock-object
				if newVal != oldUniquePropertyValue:
					if oldUniquePropertyValue is not None:
						db.Delete( db.Key.from_path( "%s_uniquePropertyIndex" % self.kindName, oldUniquePropertyValue ) )
					if newVal is not None:
						newLockObj = db.Entity( "%s_uniquePropertyIndex" % self.kindName, name=newVal )
						newLockObj["references"] = str( dbObj.key() )
						db.Put( newLockObj )
			return( str( dbObj.key() ), dbObj )
		# Allow bones to perform outstanding "magic" operations before saving to db
		for key in dir( self ):
			if "__" not in key:
				_bone = getattr( self, key )
				if( isinstance( _bone, baseBone ) ):
					_bone.performMagic( isAdd=(id==False) )
		# Run our SaveTxn
		id, dbObj = db.RunInTransactionOptions( db.TransactionOptions(xg=True), txnUpdate, id, self, clearUpdateTag )
		# Perform post-save operations (postProcessSerializedData Hook, Searchindex, ..)
		self.id.value = str(id)
		if self.searchIndex: #Add a Document to the index if an index specified
			fields = []
			for key in dir( self ):
				if "__" not in key:
					_bone = getattr( self, key )
					if( isinstance( _bone, baseBone )  ) and _bone.searchable:
						fields.extend( _bone.getSearchDocumentFields(key ) )
			if "getSearchDocumentFields" in dir( self ):
				fields = self.getSearchDocumentFields( fields )
			if fields:
				try:
					doc = search.Document(doc_id="s_"+str(id), fields= fields )
					search.Index(name=self.searchIndex).put( doc )
				except:
					pass
		for key in dir( self ):
			if "__" not in key:
				_bone = getattr( self, key )
				if( isinstance( _bone, baseBone ) ) and "postSavedHandler" in dir( _bone ):
					_bone.postSavedHandler( key, self, id, dbObj )
		if "postProcessSerializedData" in dir( self ):
			self.postProcessSerializedData( id,  dbObj )
		if not clearUpdateTag:
			updateRelations( id )
		return( id )


	def delete( self, id ):
		"""
			Deletes the specified entity from the database.
			
			@param id: DB.Key to delete
			@type id: String 
		"""
		if self.enforceUniqueValuesFor:
			#Ensure that we delete any lock objects remaining for this entry
			uniqueProperty = (self.enforceUniqueValuesFor[0] if isinstance( self.enforceUniqueValuesFor, tuple ) else self.enforceUniqueValuesFor)
			try:
				dbObj = db.Get( db.Key( id ) )
				if  "%s.uniqueIndexValue" % uniqueProperty in dbObj.keys():
					db.Delete( db.Key.from_path( "%s_uniquePropertyIndex" % self.kindName, dbObj[ "%s.uniqueIndexValue" % uniqueProperty ] ) )
			except db.EntityNotFoundError:
				pass
		db.Delete( db.Key( id ) )
		for key in dir( self ):
			if "__" not in key:
				_bone = getattr( self, key )
				if( isinstance( _bone, baseBone )  ) and "postDeletedHandler" in dir( _bone ):
					_bone.postDeletedHandler( self, key, id )
		if "postDeletedHandler" in dir( self ):
			self.postDeletedHandler( key, id )
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
						try:
							# Reading the value from db.Entity
							_bone.value = str( values.key() )
						except:
							# Is it in the dict?
							if "id" in values.keys():
								_bone.value = str( values["id"] )
							else: #Ingore the key value
								pass
					else:
						_bone.unserialize( key, values )

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
					error = _bone.fromClient( key, data )
					self.errors[ key ] = error
					if error  and _bone.required:
						complete = False
		if self.enforceUniqueValuesFor:
			uniqueProperty = (self.enforceUniqueValuesFor[0] if isinstance( self.enforceUniqueValuesFor, tuple ) else self.enforceUniqueValuesFor)
			newVal = getattr( self, uniqueProperty ).getUniquePropertyIndexValue()
			if newVal is not None:
				try:
					dbObj = db.Get( db.Key.from_path( "%s_uniquePropertyIndex" % self.kindName, newVal  ) )
					if dbObj["references"] != self.id.value: #This valus is taken (sadly, not by us)
						complete = False
						if isinstance( self.enforceUniqueValuesFor, tuple ):
							errorMsg = _(self.enforceUniqueValuesFor[1])
						else:
							errorMsg = _("This value is not avaiable")
						self.errors[ uniqueProperty ] = errorMsg
				except db.EntityNotFoundError:
					pass
		if( len( data )==0 or (len(data)==1 and "id" in data) or ("nomissing" in data.keys() and str(data["nomissing"])=="1") ):
			self.errors = {}
		return( complete )

class SkelList( list ):
	"""
		Class to hold multiple skeletons along
		other commonly used informations (cursors, etc)
		of that result set.
		
		Usually created by calling skel.all(). ... .fetch()
	"""

	def __init__( self, baseSkel ):
		"""
			@param baseSkel: The baseclass for all entries in this list
		"""
		super( SkelList, self ).__init__()
		self.baseSkel = baseSkel
		self.cursor = None


### Tasks ###

@callDeferred
def updateRelations( destID ):
	#logging.error("updateRelations %s" % destID )
	for srcRel in db.Query( "viur-relations" ).filter("dest.id =", destID ).iter( ):
		logging.error("updating ref %s" % srcRel.key().parent() )
		skel = skeletonByKind( srcRel["viur_src_kind"] )()
		skel.fromDB( str(srcRel.key().parent()) )
		for key in dir( skel ):
			if not key.startswith("_"):
				_bone = getattr( skel, key )
				if isinstance( _bone, relationalBone ):
					if isinstance( _bone.value, dict ):
						_bone.fromClient( key, {key: _bone.value["id"]} )
					elif isinstance( _bone.value, list ):
						_bone.fromClient( key, {key: [x["id"] for x in _bone.value]} )
		skel.toDB( str(srcRel.key().parent()), clearUpdateTag=True )


@CallableTask
class TaskUpdateSeachIndex( CallableTaskBase ):
	"""This tasks loads and saves *every* entity of the given modul.
	This ensures an updated searchIndex and verifies consistency of this data.
	"""
	id = "rebuildsearchIndex"
	name = u"Rebuild a Searchindex"
	descr = u"Needs to be called whenever a search-releated parameters are changed."
	direct = False

	def canCall( self ):
		"""Checks wherever the current user can execute this task
		@returns bool
		"""
		user = utils.getCurrentUser()
		return( user is not None and "root" in user["access"] )

	def dataSkel(self):
		modules = []
		for modulName in dir( conf["viur.mainApp"] ):
			modul = getattr( conf["viur.mainApp"], modulName )
			if "editSkel" in dir( modul ) and not modulName in modules:
				modules.append( modulName )
		skel = Skeleton( self.kindName )
		skel.modul = selectOneBone( descr="Modul", values={ x: x for x in modules}, required=True )
		def verifyCompact( val ):
			if not val or val.lower()=="no" or val=="YES":
				return( None )
			return("Must be \"No\" or uppercase \"YES\" (very dangerous!)")
		skel.compact = stringBone( descr="Recreate Entities", vfunc=verifyCompact, required=False, defaultValue="NO" )
		return( skel )

	def execute( self, modul=None, compact="", *args, **kwargs ):
		Skel = None
		if modul in dir( conf["viur.mainApp"] ):
			if "editSkel" in dir( getattr( conf["viur.mainApp"], modul ) ):
				Skel = getattr( conf["viur.mainApp"], modul ).editSkel
		if not Skel:
			logging.error("TaskUpdateSeachIndex: Invalid modul")
			return
		for sub in Skel().all().iter():
			try:
				skel = Skel()
				skel.fromDB( str(sub.key()) )
				if compact=="YES":
					skel.delete(str(sub.key()) )
				skel.toDB( str(sub.key()) )
			except Exception as e:
				logging.error("Updating %s failed" % str(sub.key()) )
				logging.error( e )

