# -*- coding: utf-8 -*-

from server.bones import baseBone, boneFactory, dateBone, selectOneBone, relationalBone, stringBone
from collections import OrderedDict
from threading import local
from server import db
from time import time
from google.appengine.api import search
from server.config import conf
from server import utils
from server.tasks import CallableTask, CallableTaskBase, callDeferred
import inspect, os, sys
from server.errors import ReadFromClientError
import logging, copy
from random import random


class BoneCounter(local):
	def __init__(self):
		self.count = 0

_boneCounter = BoneCounter()

class MetaSkel( type ):
	"""
		This is the meta class for Skeletons.
		It is used to enforce several restrictions on bone names, etc.
	"""
	_skelCache = {}
	__reservedKeywords_ = [ "self", "cursor", "amount", "orderby", "orderdir",
	                        "style", "items", "keys", "values" ]
	def __init__( cls, name, bases, dct ):
		kindName = cls.kindName
		if kindName and kindName in MetaSkel._skelCache.keys():
			isOkay = False
			relNewFileName = inspect.getfile(cls).replace( os.getcwd(),"" )
			relOldFileName = inspect.getfile( MetaSkel._skelCache[ kindName ] ).replace( os.getcwd(),"" )
			if relNewFileName.strip(os.path.sep).startswith("server"):
				#The currently processed skeleton is from the server.* package
				pass
			elif relOldFileName.strip(os.path.sep).startswith("server"):
				#The old one was from server - override it
				MetaSkel._skelCache[ kindName ] = cls
				isOkay = True
			else:
				raise ValueError("Duplicate definition for %s in %s and %s" % (kindName, relNewFileName, relOldFileName) )
		#	raise NotImplementedError("Duplicate definition of %s" % kindName)
		relFileName = inspect.getfile(cls).replace( os.getcwd(),"" )
		if not relFileName.strip(os.path.sep).startswith("skeletons") and not relFileName.strip(os.path.sep).startswith("server"): # and any( [isinstance(x,baseBone) for x in [ getattr(cls,y) for y in dir( cls ) if not y.startswith("_") ] ] ):
			if not "viur_doc_build" in dir(sys): #Do not check while documentation build
				raise NotImplementedError("Skeletons must be defined in /skeletons/")
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
			if key == "postProcessSerializedData":
				raise AttributeError( "postProcessSerializedData is deprecated! Use postSavedHandler instead." )
		return( super( MetaSkel, cls ).__init__( name, bases, dct ) )

def skeletonByKind( kindName ):
	if not kindName:
		return( None )
	assert kindName in MetaSkel._skelCache, "Unknown skeleton '%s'" % kindName
	return MetaSkel._skelCache[ kindName ]

def listKnownSkeletons():
	return list(MetaSkel._skelCache.keys())[:]

class Skeleton( object ):
	""" 
		This is a container-object holding information about one database entity.

		It has to be sub-classed with individual information about the kindName of the entities
		and its specific data attributes, the so called bones.
		The Skeleton stores its bones in an :class:`OrderedDict`-Instance, so the definition order of the
		contained bones remains constant.

		:ivar id: This bone stores the current database key of this entity. \
		Assigning to this bones value is dangerous and does *not* affect the actual key its stored in.
		:vartype id: server.bones.baseBone

		:ivar creationdate: The date and time where this entity has been created.
		:vartype creationdate: server.bones.dateBone

		:ivar changedate: The date and time of the last change to this entity.
		:vartype changedate: server.bones.dateBone
	"""
	__metaclass__ = MetaSkel

	def __setattr__(self, key, value):
		if "_Skeleton__isInitialized_" in dir( self ) and not key in ["_Skeleton__currentDbKey_"]:
			logging.error(key)
			raise AttributeError("You cannot directly modify the skeleton instance. Use [] instead!")
		if not "__dataDict__" in dir( self ):
			super( Skeleton, self ).__setattr__( "__dataDict__", OrderedDict() )
		if not "__" in key:
			if isinstance( value , baseBone ):
				self.__dataDict__[ key ] =  value
			elif key in self.__dataDict__.keys(): #Allow setting a bone to None again
				self.__dataDict__[ key ] =  value
		super( Skeleton, self ).__setattr__( key, value )

	def __delattr__(self, key):
		if "_Skeleton__isInitialized_" in dir( self ):
			raise AttributeError("You cannot directly modify the skeleton instance. Use [] instead!")

		if( key in dir( self ) ):
			super( Skeleton, self ).__delattr__( key )
		else:
			del self.__dataDict__[key]

	def __getattribute__(self, item):
		isOkay = False
		if item.startswith("_") or item in ["kindName","searchIndex", "enforceUniqueValuesFor","all","fromDB",
						    "toDB", "items","keys","values","setValues","getValues","errors","fromClient",
						    "preProcessBlobLocks","preProcessSerializedData","postSavedHandler",
						    "postDeletedHandler", "delete","clone","getSearchDocumentFields","subSkels",
						    "subSkel","refresh","writeRandomIndex"]:
			isOkay = True
		elif not "_Skeleton__isInitialized_" in dir( self ):
			isOkay = True
		if isOkay:
			return( super( Skeleton, self ).__getattribute__(item ))
		else:
			raise AttributeError("Use [] to access your bones!")

	def __contains__(self, item):
		return( item in self.__dataDict__.keys() )

	def items(self):
		return( self.__dataDict__.items() )

	def keys(self):
		return( self.__dataDict__.keys() )

	def values(self):
		return( self.__dataDict__.values() )

	kindName = "" # To which kind we save our data to
	searchIndex = None # If set, use this name as the index-name for the GAE search API
	enforceUniqueValuesFor = None # If set, enforce that the values of that bone are unique.
	writeRandomIndex = False # If set, allow orderby 'random' queries
	subSkels = {} # List of pre-defined sub-skeletons of this type


	# The "key" bone stores the current database key of this skeleton.
	# Warning: Assigning to this bones value is dangerous and does *not* affect the actual key
	# its stored in
	key = baseBone( descr="key", readOnly=True, visible=False )

	# The date (including time) when this entry has been created
	creationdate = dateBone( descr="created at",
	                         readOnly=True, visible=False,
	                         creationMagic=True, indexed=True  )

	# The last date (including time) when this entry has been updated
	changedate = dateBone( descr="updated at",
	                       readOnly=True, visible=False,
	                       updateMagic=True, indexed=True, )

	@classmethod
	def subSkel(cls, name, *args):
		"""
			Creates a new sub-skeleton as part of the current skeleton.

			A sub-skeleton is a copy of the original skeleton, containing only a subset of its bones.
			To define sub-skeletons, use the subSkels property of the Skeleton object.

			By passing multiple sub-skeleton names to this function, a sub-skeleton with the union of
			all bones of the specified sub-skeletons is returned.

			If an entry called "*" exists in the subSkels-dictionary, the bones listed in this entry
			will always be part of the generated sub-skeleton.

			:param name: Name of the sub-skeleton (that's the key of the subSkels dictionary); \
						Multiple names can be specified.
			:type name: str

			:return: The sub-skeleton of the specified type.
			:rtype: server.skeleton.Skeleton
		"""
		skel = cls()

		if "*" in skel.subSkels.keys():
			boneList = skel.subSkels["*"][:]
		else:
			boneList = []

		subSkelNames = [name] + list(args)

		for name in subSkelNames:
			if not name in skel.subSkels.keys():
				raise ValueError("Unknown sub-skeleton %s for skel %s" % (name, skel.kindName))
			boneList.extend( skel.subSkels[name][:] )

		for key, bone in skel.items():
			if key in ["key"]:
				keepBone = True
			else:
				keepBone = key in boneList

			if not keepBone: #Test if theres a prefix-match that allows it
				for boneKey in boneList:
					if boneKey.endswith("*") and key.startswith(boneKey[:-1]):
						keepBone = True
						break

			if not keepBone: #Remove that bone from the skeleton
				skel[key] = None

		return skel


	def __init__( self, kindName=None, _cloneFrom=None, *args,  **kwargs ):
		"""
			Initializes a Skeleton.
			
			:param kindName: If set, it overrides the kindName of the current class.
			:type kindName: str
		"""
		super(Skeleton, self).__init__(*args, **kwargs)
		self.kindName = kindName or self.kindName
		self.errors = {}
		self.__currentDbKey_ = None
		self.__dataDict__ = OrderedDict()
		if _cloneFrom:
			for key, bone in _cloneFrom.__dataDict__.items():
				self.__dataDict__[ key ] = copy.deepcopy( bone )
			if self.enforceUniqueValuesFor:
				uniqueProperty = (self.enforceUniqueValuesFor[0] if isinstance( self.enforceUniqueValuesFor, tuple ) else self.enforceUniqueValuesFor)
				if not uniqueProperty in self.keys():
					raise( ValueError("Cant enforce unique variables for unknown bone %s" % uniqueProperty ) )
		else:
			tmpList = []

			for key in dir(self):
				bone = getattr( self, key )
				if not "__" in key and isinstance( bone , boneFactory ):
					tmpList.append( (key, bone) )
			tmpList.sort( key=lambda x: x[1].idx )
			for key, bone in tmpList:
				#bone = copy.copy( bone )
				bone = bone(_kindName=self.kindName)
				self.__dataDict__[ key ] = bone
			if self.enforceUniqueValuesFor:
				uniqueProperty = (self.enforceUniqueValuesFor[0] if isinstance( self.enforceUniqueValuesFor, tuple ) else self.enforceUniqueValuesFor)
				if not uniqueProperty in [ key for (key,bone) in tmpList ]:
					raise( ValueError("Cant enforce unique variables for unknown bone %s" % uniqueProperty ) )
		self.__isInitialized_ = True

	def clone(self):
		"""
			Creates a stand-alone copy of the current Skeleton object.

			:returns: The stand-alone copy of the object.
			:rtype: Skeleton
		"""
		return( type( self )( _cloneFrom=self ) )

	def __setitem__(self, name, value):
		if value is None and name in self.__dataDict__.keys():
			del self.__dataDict__[ name ]
		elif isinstance( value, baseBone ):
			self.__dataDict__[ name ] = value
		elif isinstance( value, boneFactory ):
			self.__dataDict__[ name ] = value()
		elif value:
			raise ValueError("Expected a instance of baseBone, a boneFactory or None, got %s instead." % type(value))

	def __getitem__(self, name ):
		return( self.__dataDict__[name] )

	def __delitem__(self, key):
		del self.__dataDict__[ key ]

	def all(self):
		"""
			Create a query with the current Skeletons kindName.

			:returns: A db.Query object which allows for entity filtering and sorting.
			:rtype: :class:`server.db.Query`
		"""
		return( db.Query( self.kindName, srcSkelClass=self ) )

	def fromDB( self, key ):
		"""
			Load entity with *key* from the data store into the Skeleton.

			Reads all available data of entity kind *kindName* and the key *key*
			from the data store into the Skeleton structure's bones. Any previous
			data of the bones will discard.

			To store a Skeleton object to the data store, see :func:`~server.skeleton.Skeleton.toDB`.

			:param key: A :class:`server.DB.Key`, :class:`server.DB.Query`, or string,\
			from which the data shall be fetched.
			:type key: server.DB.Key | DB.Query | str

			:returns: True on success; False if the given key could not be found.
			:rtype: bool

		"""
		if isinstance(key, basestring ):
			try:
				key = db.Key( key )
			except db.BadKeyError:
				key = unicode( key )
				if key.isdigit():
					key = long( key )
				elif not len(key):
					raise ValueError("fromDB called with empty key!")
				key = db.Key.from_path( self.kindName, key )
		if not isinstance( key, db.Key ):
			raise ValueError("fromDB expects an db.Key instance, an string-encoded key or a long as argument, got \"%s\" instead" % key )
		if key.kind() !=  self.kindName: # Wrong Kind
			return( False )
		try:
			dbRes = db.Get( key )
		except db.EntityNotFoundError:
			return( False )
		if dbRes is None:
			return( False )
		self.setValues( dbRes )
		key = str( dbRes.key() )
		self.__currentDbKey_ = key
		return( True )

	def toDB( self, clearUpdateTag=False ):
		"""
			Store current Skeleton entity to data store.

			Stores the current data of this instance into the database.
			If an *key* value is set to the object, this entity will ne updated;
			Otherwise an new entity will be created.

			To read a Skeleton object from the data store, see :func:`~server.skeleton.Skeleton.fromDB`.

			:param clearUpdateTag: If True, this entity won't be marked dirty;
			This avoids from being fetched by the background task updating relations.
			:type clearUpdateTag: bool

			:returns: The data store key of the entity.
			:rtype: str
		"""
		def txnUpdate( key, mergeFrom, clearUpdateTag ):
			blobList = set()
			skel = type(mergeFrom)()
			# Load the current values from Datastore or create a new, empty db.Entity
			if not key:
				dbObj = db.Entity( skel.kindName )
				oldBlobLockObj = None
			else:
				k = db.Key( key )
				assert k.kind()==skel.kindName, "Cannot write to invalid kind!"
				try:
					dbObj = db.Get( k )
				except db.EntityNotFoundError:
					dbObj = db.Entity( k.kind(), id=k.id(), name=k.name(), parent=k.parent() )
				else:
					skel.setValues( dbObj )
				try:
					oldBlobLockObj = db.Get(db.Key.from_path("viur-blob-locks",str(k)))
				except:
					oldBlobLockObj = None
			if skel.enforceUniqueValuesFor: # Remember the old lock-object (if any) we might need to delete
				uniqueProperty = (skel.enforceUniqueValuesFor[0] if isinstance( skel.enforceUniqueValuesFor, tuple ) else skel.enforceUniqueValuesFor)
				if "%s.uniqueIndexValue" % uniqueProperty in dbObj.keys():
					oldUniquePropertyValue = dbObj[ "%s.uniqueIndexValue" % uniqueProperty ]
				else:
					oldUniquePropertyValue = None

			# Merge the values from mergeFrom in
			for key, bone in skel.items():
				if key in mergeFrom.keys() and mergeFrom[ key ]:
					bone.mergeFrom( mergeFrom[ key ] )

			unindexed_properties = []
			for key, _bone in skel.items():
				tmpKeys = dbObj.keys()
				dbObj = _bone.serialize( key, dbObj )
				newKeys = [ x for x in dbObj.keys() if not x in tmpKeys ] #These are the ones that the bone added
				if not _bone.indexed:
					unindexed_properties += newKeys
				blobList.update( _bone.getReferencedBlobs() )
				#if _bone.searchable and not skel.searchIndex:
				#	tags += [ tag for tag in _bone.getSearchTags() if (tag not in tags and len(tag)<400) ]
			#if tags:
			#	dbObj["viur_tags"] = tags
			if clearUpdateTag:
				dbObj["viur_delayed_update_tag"] = 0 #Mark this entity as Up-to-date.
			else:
				dbObj["viur_delayed_update_tag"] = time() #Mark this entity as dirty, so the background-task will catch it up and update its references.
			dbObj.set_unindexed_properties( unindexed_properties )
			dbObj = skel.preProcessSerializedData( dbObj )
			if self.writeRandomIndex: # Write our Random-Index if requested
				dbObj["viur_randomidx"] = random()
			if skel.enforceUniqueValuesFor:
				uniqueProperty = (skel.enforceUniqueValuesFor[0] if isinstance( skel.enforceUniqueValuesFor, tuple ) else skel.enforceUniqueValuesFor)
				# Check if the property is really unique
				newVal = skel[ uniqueProperty ].getUniquePropertyIndexValue()
				lockObj = None
				if newVal is not None:
					try:
						lockObj = db.Get( db.Key.from_path( "%s_uniquePropertyIndex" % skel.kindName, newVal ) )
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
				for key, _bone in skel.items():
					if _bone.searchable:
						tags += [ tag for tag in _bone.getSearchTags() if (tag not in tags and len(tag)<400) ]
				dbObj["viur_tags"] = tags
			db.Put( dbObj ) #Write the core entry back
			# Now write the blob-lock object
			blobList = skel.preProcessBlobLocks( blobList )
			if blobList is None:
				raise ValueError("Did you forget to return the bloblist somewhere inside getReferencedBlobs()?")
			if oldBlobLockObj is not None:
				oldBlobs = set(oldBlobLockObj["active_blob_references"] if oldBlobLockObj["active_blob_references"] is not None else [])
				removedBlobs = oldBlobs-blobList
				oldBlobLockObj["active_blob_references"] = list(blobList)
				if oldBlobLockObj["old_blob_references"] is None:
					oldBlobLockObj["old_blob_references"] = [x for x in removedBlobs]
				else:
					tmp = set(oldBlobLockObj["old_blob_references"]+[x for x in removedBlobs])
					oldBlobLockObj["old_blob_references"] = [x for x in (tmp-blobList)]
				oldBlobLockObj["has_old_blob_references"] = oldBlobLockObj["old_blob_references"] is not None and len(oldBlobLockObj["old_blob_references"])>0
				oldBlobLockObj["is_stale"] = False
				db.Put( oldBlobLockObj )
			else: #We need to create a new blob-lock-object
				blobLockObj = db.Entity( "viur-blob-locks", name=str( dbObj.key() ) )
				blobLockObj["active_blob_references"] = list(blobList)
				blobLockObj["old_blob_references"] = []
				blobLockObj["has_old_blob_references"] = False
				blobLockObj["is_stale"] = False
				db.Put( blobLockObj )
			if skel.enforceUniqueValuesFor:
				# Now update/create/delete the lock-object
				if newVal != oldUniquePropertyValue or not lockObj:
					if oldUniquePropertyValue is not None:
						try:
							db.Delete( db.Key.from_path( "%s_uniquePropertyIndex" % skel.kindName, oldUniquePropertyValue ) )
						except:
							logging.warning("Cannot delete stale lock-object")
					if newVal is not None:
						newLockObj = db.Entity( "%s_uniquePropertyIndex" % skel.kindName, name=newVal )
						newLockObj["references"] = str( dbObj.key() )
						db.Put( newLockObj )
			return( str( dbObj.key() ), dbObj, skel )
		# END of txnUpdate subfunction

		key = self.__currentDbKey_
		if not isinstance(clearUpdateTag,bool):
			raise ValueError("Got an unsupported type %s for clearUpdateTag. toDB doesn't accept a key argument any more!" % str(type(clearUpdateTag)))

		# Allow bones to perform outstanding "magic" operations before saving to db
		for bkey,_bone in self.items():
			_bone.performMagic( isAdd=(key==None) )

		# Run our SaveTxn
		if db.IsInTransaction():
			key, dbObj, skel = txnUpdate(key, self, clearUpdateTag)
		else:
			key, dbObj, skel = db.RunInTransactionOptions(db.TransactionOptions(xg=True),
			                                                txnUpdate, key, self, clearUpdateTag)

		# Perform post-save operations (postProcessSerializedData Hook, Searchindex, ..)
		self["key"].value = str(key)
		self.__currentDbKey_ = str(key)
		if self.searchIndex: #Add a Document to the index if an index specified
			fields = []

			for boneName, bone in skel.items():
				if bone.searchable:
					fields.extend(bone.getSearchDocumentFields(boneName))

			fields = skel.getSearchDocumentFields( fields )
			if fields:
				try:
					doc = search.Document(doc_id="s_"+str(key), fields= fields )
					search.Index(name=skel.searchIndex).put( doc )
				except:
					pass

			else: #Remove the old document (if any)
				try:
					search.Index( name=self.searchIndex ).remove( "s_"+str(key) )
				except:
					pass

		for boneName, bone in skel.items():
			bone.postSavedHandler(boneName, skel, key, dbObj)

		skel.postSavedHandler(key, dbObj)

		if not clearUpdateTag:
			updateRelations(key, time() + 1)

		return( key )


	def preProcessBlobLocks(self, locks):
		"""
			Can be overridden to modify the list of blobs referenced by this skeleton
		"""
		return( locks )

	def preProcessSerializedData(self, entity):
		"""
			Can be overridden to modify the :class:`server.db.Entity` before its actually
			written to the data store.
		"""
		return( entity )

	def getSearchDocumentFields(self, fields):
		"""
			Can be overridden to modify the list of search document fields before they are
			added to the index.
		"""
		return( fields )

	def postSavedHandler(self, key, dbObj ):
		"""
			Can be overridden to perform further actions after the entity has been written
			to the data store.
		"""
		pass

	def postDeletedHandler(self, key):
		"""
			Can be overridden to perform further actions after the entity has been deleted
			from the data store.
		"""


	def delete( self ):
		"""
			Deletes the entity associated with the current Skeleton from the data store.
		"""
		def txnDelete( key ):
			if self.enforceUniqueValuesFor:
				#Ensure that we delete any lock objects remaining for this entry
				uniqueProperty = (self.enforceUniqueValuesFor[0] if isinstance( self.enforceUniqueValuesFor, tuple ) else self.enforceUniqueValuesFor)
				try:
					dbObj = db.Get( db.Key( key ) )
					if  "%s.uniqueIndexValue" % uniqueProperty in dbObj.keys():
						db.Delete( db.Key.from_path( "%s_uniquePropertyIndex" % self.kindName, dbObj[ "%s.uniqueIndexValue" % uniqueProperty ] ) )
				except db.EntityNotFoundError:
					pass
			# Delete the blob-key lock object
			try:
				lockObj = db.Get(db.Key.from_path("viur-blob-locks", str(key)))
			except:
				lockObj = None
			if lockObj is not None:
				if lockObj["old_blob_references"] is None and lockObj["active_blob_references"] is None:
					db.Delete( lockObj ) #Nothing to do here
				elif lockObj["old_blob_references"] is None:
					lockObj["old_blob_references"] = lockObj["active_blob_references"]
				elif lockObj["active_blob_references"] is None:
					pass #Nothing to do here
				else:
					lockObj["old_blob_references"] += lockObj["active_blob_references"]
				lockObj["active_blob_references"] = []
				lockObj["is_stale"] = True
				lockObj["has_old_blob_references"] = True
				db.Put(lockObj)
			db.Delete( db.Key( key ) )
		key = self.__currentDbKey_
		if key is None:
			raise ValueError("This skeleton is not in the database (anymore?)!")
		skel = type( self )()
		if not skel.fromDB( key ):
			raise ValueError("This skeleton is not in the database (anymore?)!")
		db.RunInTransactionOptions(db.TransactionOptions(xg=True), txnDelete, key )
		for boneName, _bone in skel.items():
			_bone.postDeletedHandler( skel, boneName, key )
		skel.postDeletedHandler( key )
		if self.searchIndex:
			try:
				search.Index( name=self.searchIndex ).remove( "s_"+str(key) )
			except:
				pass
		self.__currentDbKey_ = None

	def setValues( self, values, key=False ):
		"""
			Load *values* into Skeleton, without validity checks.

			This function is usually used to merge values fetched from the database into the
			current skeleton instance.

			:warning: Performs no error-checking for invalid values! Its possible to set invalid values
			which may break the serialize/deserialize function of the related bone!

			If no bone could be found for a given key, this key is ignored. Any values of other bones
			not mentioned in *values* remain unchanged.
			
			:param values: A dictionary with values.
			:type values: dict
			:param key: If given, this allows to set the current database unique key.
			:type key: server.db.Key | None
		"""
		for bkey,_bone in self.items():
			if isinstance( _bone, baseBone ):
				if bkey=="key":
					try:
						# Reading the value from db.Entity
						_bone.value = str( values.key() )
					except:
						# Is it in the dict?
						if "key" in values.keys():
							_bone.value = str( values["key"] )
						else: #Ingore the key value
							pass
				else:
					_bone.unserialize( bkey, values )

		if key is not False:
			assert key is None or isinstance( key, db.Key ), "Key must be None or a db.Key instance"

			if key is None:
				self.__currentDbKey_ = None
				self["key"].value = ""
			else:
				self.__currentDbKey_ = str( key )
				self["key"].value = self.__currentDbKey_

	def getValues(self):
		"""
			Returns the current bones of the Skeleton as a dictionary.

			:returns: Dictionary, where the keys are the bones and the values the current values.
			:rtype: dict
		"""
		res = {}

		for key,_bone in self.items():
			res[ key ] = _bone.value

		return( res )

	def fromClient( self, data ):
		"""
			Load supplied *data* into Skeleton.

			This function works similar to :func:`~server.skeleton.Skeleton.setValues`, except that
			the values retrieved from *data* are checked against the bones and their validity checks.

			Even if this function returns False, all bones are guaranteed to be in a valid state.
			The ones which have been read correctly are set to their valid values;
			Bones with invalid values are set back to a safe default (None in most cases).
			So its possible to call :func:`~server.skeleton.Skeleton.toDB` afterwards even if reading
			data with this function failed (through this might violates the assumed consistency-model).
			
			:param data: Dictionary from which the data is read.
			:type data: dict

			:returns: True if all data was successfully read and taken by the Skeleton's bones.\
			False otherwise (eg. some required fields where missing or invalid).
			:rtype: bool
		"""
		complete = True
		super(Skeleton,self).__setattr__( "errors", {} )

		for key, _bone in self.items():
			if _bone.readOnly:
				continue

			error = _bone.fromClient( key, data )
			if isinstance( error, ReadFromClientError ):
				self.errors.update( error.errors )
				if error.forceFail:
					complete = False
			else:
				self.errors[ key ] = error

			if error  and _bone.required:
				complete = False
				logging.info("%s throws error: %s" % (key, error))

		if self.enforceUniqueValuesFor:
			uniqueProperty = (self.enforceUniqueValuesFor[0] if isinstance( self.enforceUniqueValuesFor, tuple ) else self.enforceUniqueValuesFor)
			newVal = self[ uniqueProperty].getUniquePropertyIndexValue()
			if newVal is not None:
				try:
					dbObj = db.Get( db.Key.from_path( "%s_uniquePropertyIndex" % self.kindName, newVal  ) )
					if dbObj["references"] != self["key"].value: #This valus is taken (sadly, not by us)
						complete = False
						if isinstance( self.enforceUniqueValuesFor, tuple ):
							errorMsg = _(self.enforceUniqueValuesFor[1])
						else:
							errorMsg = _("This value is not available")
						self.errors[ uniqueProperty ] = errorMsg
				except db.EntityNotFoundError:
					pass

		if( len(data) == 0
		    or (len(data) == 1 and "key" in data)
		    or ("nomissing" in data.keys() and str(data["nomissing"]) == "1" )):
			super(Skeleton,self).__setattr__( "errors", {} )

		return( complete )

	def refresh(self):
		"""
			Refresh the bones current content.

			This function causes a refresh of all relational bones and their associated
			information.
		"""
		for key,bone in self.items():
			if not isinstance( bone, baseBone ):
				continue
			if "refresh" in dir( bone ):
				bone.refresh( key, self )


class MetaRelSkel( type ):
	"""
		Meta Class for relational Skeletons.
		Used to enforce several restrictions on Bone names etc.
	"""
	_skelCache = {}
	__reservedKeywords_ = [ "self", "cursor", "amount", "orderby", "orderdir", "style" ]
	def __init__( cls, name, bases, dct ):
		for key in dir( cls ):
			if isinstance( getattr( cls, key ), baseBone ):
				if key.lower()!=key:
					raise AttributeError( "Bonekeys must be lowercase" )
				if "." in key:
					raise AttributeError( "Bonekeys cannot not contain a dot (.) - got %s" % key )
				if key in MetaRelSkel.__reservedKeywords_:
					raise AttributeError( "Your bone cannot have any of the following keys: %s" % str( MetaRelSkel.__reservedKeywords_ ) )
			if key == "postProcessSerializedData":
				raise AttributeError( "postProcessSerializedData is deprecated! Use postSavedHandler instead." )
		return( super( MetaRelSkel, cls ).__init__( name, bases, dct ) )


class RelSkel( object ):
	"""
		This is a Skeleton-like class that acts as a container for Skeletons used as a
		additional information data skeleton for
		:class:`~server.bones.extendedRelationalBone.extendedRelationalBone`.

		It needs to be sub-classed where information about the kindName and its attributes
		(bones) are specified.

		The Skeleton stores its bones in an :class:`OrderedDict`-Instance, so the definition order of the
		contained bones remains constant.
	"""
	__metaclass__ = MetaRelSkel

	def __setattr__(self, key, value):
		if "_Skeleton__isInitialized_" in dir( self ) and not key in ["_Skeleton__currentDbKey_"]:
			raise AttributeError("You cannot directly modify the skeleton instance. Use [] instead!")
		if not "__dataDict__" in dir( self ):
			super( RelSkel, self ).__setattr__( "__dataDict__", OrderedDict() )
		if not "__" in key:
			if isinstance( value , baseBone ):
				self.__dataDict__[ key ] =  value
			elif key in self.__dataDict__.keys(): #Allow setting a bone to None again
				self.__dataDict__[ key ] =  value
		super( RelSkel, self ).__setattr__( key, value )

	def __delattr__(self, key):
		if "_Skeleton__isInitialized_" in dir( self ):
			raise AttributeError("You cannot directly modify the skeleton instance. Use [] instead!")

		if( key in dir( self ) ):
			super( RelSkel, self ).__delattr__( key )
		else:
			del self.__dataDict__[key]

	def __getattribute__(self, item):
		isOkay = False
		if item.startswith("_") or item in [ "items","keys","values","setValues","errors","fromClient" ]:
			isOkay = True
		elif not "_Skeleton__isInitialized_" in dir( self ):
			isOkay = True
		if isOkay:
			return( super( RelSkel, self ).__getattribute__(item ))
		else:
			raise AttributeError("Use [] to access your bones!")

	def __contains__(self, item):
		return( item in self.__dataDict__.keys() )

	def items(self):
		return( self.__dataDict__.items() )

	def keys(self):
		return( self.__dataDict__.keys() )

	def values(self):
		return( self.__dataDict__.values() )

	def __init__( self, *args,  **kwargs ):
		"""
			Create a local copy from the global Skel-class.

			@param kindName: If set, override the entity kind were operating on.
			@type kindName: String or None
		"""
		super(RelSkel, self).__init__(*args, **kwargs)
		self.errors = {}
		self.__dataDict__ = OrderedDict()
		tmpList = []
		for key in dir(self):
			bone = getattr( self, key )
			if not "__" in key and isinstance( bone , boneFactory ):
				tmpList.append( (key, bone) )
		tmpList.sort( key=lambda x: x[1].idx )
		for key, bone in tmpList:
			bone = bone() #copy.copy( bone )
			self.__dataDict__[ key ] = bone
		self.__isInitialized_ = True

	key = baseBone( descr="key", readOnly=True, visible=False )

	@classmethod
	def fromSkel(cls, skelCls, *args):
		"""
			Creates a relSkel from a skeleton-class using only the bones explicitly named
			in *args
		:param skelCls:
		:param args:
		:return:
		"""
		skel = cls()
		skel.__isInitialized_ = False
		for key in args:
			if key in dir(skelCls):
				skel[key] = getattr(skelCls, key)(_kindName=skelCls.kindName)
		skel.__isInitialized_ = True
		return skel

	def __setitem__(self, name, value):
		if value is None and name in self.__dataDict__.keys():
			del self.__dataDict__[ name ]
		elif isinstance( value, baseBone ):
			self.__dataDict__[ name ] = value
		elif isinstance( value, boneFactory ):
			self.__dataDict__[ name ] = value()
		else:
			raise ValueError("Expected a instance of baseBone, a boneFactory or None, got %s instead." % type(value))

	def __getitem__(self, name ):
		return( self.__dataDict__[name] )

	def __delitem__(self, key):
		del self.__dataDict__[ key ]

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
		super(RelSkel,self).__setattr__( "errors", {} )
		for key,_bone in self.items():
			if _bone.readOnly:
				continue
			error = _bone.fromClient( key, data )
			if isinstance( error, ReadFromClientError ):
				self.errors.update( error.errors )
				if error.forceFail:
					complete = False
			else:
				self.errors[ key ] = error
			if error  and _bone.required:
				complete = False
		if( len( data )==0 or (len(data)==1 and "key" in data) or ("nomissing" in data.keys() and str(data["nomissing"])=="1") ):
			self.errors = {}
		return( complete )

	def serialize(self):
		class FakeEntity(dict):
			def set(self, key, value, indexed=False):
				self[key] = value
		dbObj = FakeEntity()
		for key, _bone in self.items():
			dbObj = _bone.serialize( key, dbObj )
		if "key" in self.keys(): #Write the key seperatly, as the base-bone doesn't store it
			dbObj["key"] = self["key"].value
		return dbObj

	def unserialize(self, values):
		"""
			Loads 'values' into this skeleton
		:param values:
		:return:
		"""
		for bkey,_bone in self.items():
			if isinstance( _bone, baseBone ):
				if bkey=="key":
					try:
						# Reading the value from db.Entity
						_bone.value = str( values.key() )
					except:
						# Is it in the dict?
						if "key" in values.keys():
							_bone.value = str( values["key"] )
						else: #Ingore the key value
							pass
				else:
					_bone.unserialize( bkey, values )


class SkelList( list ):
	"""
		This class is used to hold multiple skeletons together with other, commonly used information.

		SkelLists are returned by Skel().all()...fetch()-constructs and provide additional information
		about the data base query, for fetching additional entries.

		:ivar cursor: Holds the cursor within a query.
		:vartype cursor: str
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
def updateRelations( destID, minChangeTime, cursor=None ):
	logging.debug("Starting updateRelations for %s ; minChangeTime %s", destID, minChangeTime)
	updateListQuery = db.Query( "viur-relations" ).filter("dest.key =", destID ).filter("viur_delayed_update_tag <",minChangeTime)
	if cursor:
		updateListQuery.cursor( cursor )
	updateList = updateListQuery.run(limit=5)
	for srcRel in updateList:
		skel = skeletonByKind( srcRel["viur_src_kind"] )()
		if not skel.fromDB( str(srcRel.key().parent()) ):
			logging.warning("Cannot update stale reference to %s (referenced from %s)" % (str(srcRel.key().parent()), str(srcRel.key())))
			continue
		for key,_bone in skel.items():
			_bone.refresh( key, skel )
		skel.toDB( clearUpdateTag=True )
	if len(updateList)==5:
		updateRelations( destID, minChangeTime, updateListQuery.getCursor().urlsafe() )


@CallableTask
class TaskUpdateSearchIndex( CallableTaskBase ):
	"""
	This tasks loads and saves *every* entity of the given module.
	This ensures an updated searchIndex and verifies consistency of this data.
	"""
	key = "rebuildsearchIndex"
	name = u"Rebuild search index"
	descr = u"This task can be called to update search indexes and relational information."

	direct = True

	def canCall( self ):
		"""
		Checks wherever the current user can execute this task
		:returns: bool
		"""
		user = utils.getCurrentUser()
		return user is not None and "root" in user["access"]

	def dataSkel(self):
		modules = ["*"] + listKnownSkeletons()

		skel = Skeleton(self.kindName)

		skel["module"] = selectOneBone( descr="Module", values={ x: x for x in modules}, required=True )
		def verifyCompact( val ):
			if not val or val.lower()=="no" or val=="YES":
				return( None )
			return("Must be \"No\" or uppercase \"YES\" (very dangerous!)")
		skel["compact"] = stringBone( descr="Recreate Entities", vfunc=verifyCompact, required=False, defaultValue="NO" )

		return( skel )


	def execute( self, module, compact="", *args, **kwargs ):
		if module == "*":
			for module in listKnownSkeletons():
				logging.info("Rebuilding search index for module '%s'" % module)
				processChunk(module, compact, None)
		else:
			processChunk(module, compact, None)

@callDeferred
def processChunk(module, compact, cursor, allCount = 0):
	"""
		Processes 100 Entries and calls the next batch
	"""
	Skel = skeletonByKind( module )
	if not Skel:
		logging.error("TaskUpdateSearchIndex: Invalid module")
		return

	query = Skel().all().cursor( cursor )
	count = 0

	for key in query.run(100, keysOnly=True):
		count += 1

		try:
			skel = Skel()
			skel.fromDB(str(key))
			if compact=="YES":
				raise NotImplementedError() #FIXME: This deletes the __currentKey__ property..
				skel.delete()
			skel.refresh()
			skel.toDB()

		except Exception as e:
			logging.error("Updating %s failed" % str(key) )
			logging.exception( e )

	newCursor = query.getCursor()

	logging.info("END processChunk %s, %d records refreshed" % (module, count))
	if count and newCursor and newCursor.urlsafe() != cursor:
		# Start processing of the next chunk
		processChunk(module, compact, newCursor.urlsafe(), allCount + count)
	else:
		try:
			utils.sendEMailToAdmins("Rebuild search index finished for %s" % module,
			                        "ViUR finished to rebuild the search index for module %s.\n"
			                        "%d records updated in total on this kind." % (module, allCount))
		except: #OverQuota, whatever
			pass



### UPDATE ONE FUCKING ENTITY ###

@CallableTask
class TaskUpdateOneEntity(CallableTaskBase):
	"""
	This tasks loads and saves *one* entity with the given key.
	This ensures an updated searchIndex and verifies consistency of this data.
	
	It shall be used for debug and testing purposes.
	"""
	key = "updateoneentity"
	name = u"Refresh single entity"
	descr = u"This task can be called to update search indexes and relational information of ONE entitiy."
	direct = True

	def canCall( self ):
		"""Checks wherever the current user can execute this task
		@returns bool
		"""
		user = utils.getCurrentUser()
		return user is not None and "root" in user["access"]

	def dataSkel(self):
		skel = Skeleton(self.kindName)
		skel["key"] = stringBone(descr=u"Entity key", required=True)
		return skel

	def execute(self, key, *args, **kwargs):
		logging.info("key %s" % key)

		dkey = db.Key(encoded=str(key))
		kindName = dkey.kind()
		logging.info("kindName %s" % kindName)

		Skel = skeletonByKind(kindName)
		if not Skel:
			logging.error("No Skeleton class found for kindName %s" % kindName)
			return

		skel = Skel()
		if not skel.fromDB(str(key)):
			logging.error("The key %s could not be loaded" % key)
			return

		skel.refresh()
		skel.toDB()

		logging.info("OK")
