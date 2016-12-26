# -*- coding: utf-8 -*-

from server import db, utils, conf, errors
from server.bones import baseBone, boneFactory, dateBone, selectOneBone, relationalBone, stringBone
from server.tasks import CallableTask, CallableTaskBase, callDeferred
from collections import OrderedDict
from threading import local
from time import time
import inspect, os, sys, logging, copy
from google.appengine.api import search

try:
	import pytz
except:
	pytz = None

class BoneCounter(local):
	def __init__(self):
		self.count = 0

_boneCounter = BoneCounter()

__undefindedC__ = object()

class MetaBaseSkel(type):
	"""
		This is the meta class for Skeletons.
		It is used to enforce several restrictions on bone names, etc.
	"""
	_skelCache = {}

	__reservedKeywords_ = [ "self", "cursor", "amount", "orderby", "orderdir",
	                        "style", "items", "keys", "values" ]

	def __init__(cls, name, bases, dct):
		for key in dir(cls):
			if isinstance(getattr(cls, key), baseBone):
				if "." in key:
					raise AttributeError("Invalid bone '%s': Bone keys may not contain a dot (.)" % key )
				if key in MetaBaseSkel.__reservedKeywords_:
					raise AttributeError("Invalid bone '%s': Bone cannot have any of the following names: %s" %
					                     (key, str(MetaBaseSkel.__reservedKeywords_)))
		super(MetaBaseSkel, cls).__init__(name, bases, dct)

def skeletonByKind(kindName):
	if not kindName:
		return None

	assert kindName in MetaBaseSkel._skelCache, "Unknown skeleton '%s'" % kindName
	return MetaBaseSkel._skelCache[kindName]

def listKnownSkeletons():
	return list(MetaBaseSkel._skelCache.keys())[:]


class BaseSkeleton(object):
	""" 
		This is a container-object holding information about one database entity.

		It has to be sub-classed with individual information about the kindName of the entities
		and its specific data attributes, the so called bones.
		The Skeleton stores its bones in an :class:`OrderedDict`-Instance, so the definition order of the
		contained bones remains constant.

		:ivar key: This bone stores the current database key of this entity. \
		Assigning to this bones value is dangerous and does *not* affect the actual key its stored in.
		:vartype key: server.bones.baseBone

		:ivar creationdate: The date and time where this entity has been created.
		:vartype creationdate: server.bones.dateBone

		:ivar changedate: The date and time of the last change to this entity.
		:vartype changedate: server.bones.dateBone
	"""
	__metaclass__ = MetaBaseSkel

	def __setattr__(self, key, value):
		if "_BaseSkeleton__isInitialized_" in dir(self):
			if not key in ["valuesCache", "isClonedInstance"] and not self.isClonedInstance:
				raise AttributeError("You cannot directly modify the skeleton instance. Grab a copy using .clone() first!")
			if not "__dataDict__" in dir( self ):
				super(BaseSkeleton, self).__setattr__("__dataDict__", OrderedDict())
			if not "__" in key and key != "isClonedInstance":
				if isinstance(value , baseBone):
					self.__dataDict__[key] =  value
					self.valuesCache[key] = value.getDefaultValue()
				elif value is None and key in self.__dataDict__.keys(): #Allow setting a bone to None again
					del self.__dataDict__[key]
				elif key not in ["valuesCache"]:
					raise ValueError("You tried to do what?")
		super(BaseSkeleton, self).__setattr__(key, value)

	def __delattr__(self, key):
		if "_BaseSkeleton__isInitialized_" in dir(self) and not self.isClonedInstance:
			raise AttributeError("You cannot directly modify the skeleton instance. Grab a copy using .clone() first!")
		del self.__dataDict__[key]

	def __getattribute__(self, item):
		isOkay = False
		if item.startswith("_") or item in ["kindName","searchIndex","all","fromDB",
						    "toDB", "items","keys","values","setValues","getValues","errors","fromClient",
						    "preProcessBlobLocks","preProcessSerializedData","postSavedHandler",
						    "postDeletedHandler", "delete","clone","getSearchDocumentFields","subSkels",
						    "subSkel","refresh", "valuesCache", "getValuesCache", "setValuesCache",
						    "isClonedInstance", "setBoneValue", "unserialize", "serialize", "ensureIsCloned"]:
			isOkay = True
		elif not "_BaseSkeleton__isInitialized_" in dir(self):
			isOkay = True
		if isOkay:
			return( super(BaseSkeleton, self).__getattribute__(item ))
		elif item in self.__dataDict__.keys():
			return self.__dataDict__[item]
		else:
			raise AttributeError("Use [] to access your bones!")

	def __contains__(self, item):
		return item in self.__dataDict__.keys()

	def items(self):
		return self.__dataDict__.items()

	def keys(self):
		return self.__dataDict__.keys()

	def values(self):
		return self.__dataDict__.values()


	@classmethod
	def subSkel(cls, name, *args, **kwargs):
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
		cloned = kwargs.get("cloned", False)
		skel = cls(cloned=cloned)
		skel.isClonedInstance = True  # Unlock that skel for a moment sothat we can remove bones (which is a safe operation)

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
				delattr(skel, key)

		skel.isClonedInstance = cloned  # Relock it if necessary
		return skel

	def __init__( self, cloned=False, _cloneFrom=None, *args,  **kwargs ):
		"""
			Initializes a Skeleton.
			
			:param kindName: If set, it overrides the kindName of the current class.
			:type kindName: str
		"""
		super(BaseSkeleton, self).__init__(*args, **kwargs)
		self.errors = {}
		self.__dataDict__ = OrderedDict()
		self.valuesCache = {}
		if _cloneFrom:
			for key, bone in _cloneFrom.__dataDict__.items():
				self.__dataDict__[key] = copy.deepcopy(bone)
				self.__dataDict__[key].isClonedInstance = True
			self.valuesCache = copy.deepcopy(_cloneFrom.valuesCache)
			self.isClonedInstance = True
			self.errors = copy.deepcopy(_cloneFrom.errors)
		else:
			tmpList = []
			for key in dir(self):
				bone = getattr(self, key)
				if not "__" in key and isinstance(bone , baseBone):
					tmpList.append((key, bone))
			tmpList.sort(key=lambda x: x[1].idx)
			#logging.error(tmpList)
			for key, bone in tmpList:
				if cloned:
					self.__dataDict__[key] = copy.deepcopy(bone)
					self.__dataDict__[key].isClonedInstance = True
				else:
					self.__dataDict__[key] = bone
				self.valuesCache[key] = bone.getDefaultValue()
			self.isClonedInstance = cloned
		if "enforceUniqueValuesFor" in dir(self) and self.enforceUniqueValuesFor is not None:
			raise NotImplementedError("enforceUniqueValuesFor is not supported anymore. Set unique=True on your bone.")
		self.__isInitialized_ = True

	def setValuesCache(self, cache):
		self.valuesCache = cache

	def getValuesCache(self):
		return self.valuesCache

	def clone(self):
		"""
			Creates a stand-alone copy of the current Skeleton object.

			:returns: The stand-alone copy of the object.
			:rtype: Skeleton
		"""
		return type(self)(_cloneFrom=self)

	def ensureIsCloned(self):
		"""
			Ensure that we are a instance that can be modified.
			If we are, just self is returned (it's a no-op), otherwise
			we'll return a cloned copy.

			:return: A copy from self or just self itself
			:rtype: BaseSkeleton
		"""
		if self.isClonedInstance:
			return self
		else:
			return self.clone()

	def __setitem__(self, key, value):
		if isinstance(value, baseBone):
			raise AttributeError("Don't assign this bone object as skel[\"%s\"] = ... anymore to the skeleton. "
			                        "Use skel.%s = ... for bone to skeleton assignment!" % (key, key))

		self.valuesCache[key] = value
		#if not self.isClonedInstance:
		#	raise AttributeError("You cannot modify this Skeleton. Grab a copy using .clone() first")
		#if value is None and name in self.__dataDict__.keys():
		#	del self.__dataDict__[ name ]
		#elif isinstance( value, baseBone ):
		#	self.__dataDict__[ name ] = value
		#elif value:
		#	raise ValueError("Expected a instance of baseBone or None, got %s instead." % type(value))

	def __getitem__(self, key):
		return self.valuesCache.get(key, None)

	def __delitem__(self, key):
		del self.valuesCache[key]
		#del self.__dataDict__[ key ]

	def setValues(self, values, key=False):
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
						self.valuesCache[bkey] = str( values.key() )
					except:
						# Is it in the dict?
						if "key" in values.keys():
							self.valuesCache[bkey] = str( values["key"] )
						else: #Ingore the key value
							pass
				else:
					_bone.unserialize( self.valuesCache, bkey, values )

		if key is not False:
			assert key is None or isinstance( key, db.Key ), "Key must be None or a db.Key instance"

			if key is None:
				self["key"].value = ""
			else:
				self["key"] = str( key )

	def getValues(self):
		"""
			Returns the current bones of the Skeleton as a dictionary.

			:returns: Dictionary, where the keys are the bones and the values the current values.
			:rtype: dict
		"""
		return self.valuesCache

	def setBoneValue(self, boneName, value, append=False):
		"""
			Allow setting a bones value without calling fromClient or assigning to valuesCache directly.
			Santy-Checks are performed; if the value is invalid, that bone flips back to its original
			(default) value and false is returned.

			:param boneName: The Bone which should be modified
			:type boneName: str
			:param value: The value that should be assigned. It's type depends on the type of that bone
			:type value: object
			:param append: If true, the given value is appended to the values of that bone instead of
				replacing it. Only supported on bones with multiple=True
			:type append: bool
			:return: Wherever that operation succeeded or not.
			:rtype: bool
		"""
		bone = getattr(self, boneName, None)
		if not isinstance(bone, baseBone):
			raise ValueError("%s is no valid bone on this skeleton (%s)" % (boneName, str(self)))
		return bone.setBoneValue(self.valuesCache, boneName, value, append)

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
		super(BaseSkeleton, self).__setattr__("errors", {})

		for key, _bone in self.items():
			if _bone.readOnly:
				continue
			error = _bone.fromClient( self.valuesCache, key, data )
			if isinstance( error, errors.ReadFromClientError ):
				self.errors.update( error.errors )
				if error.forceFail:
					complete = False
			else:
				self.errors[ key ] = error

			if error  and _bone.required:
				complete = False
				logging.info("%s throws error: %s" % (key, error))

		for boneName, boneInstance in self.items():
			if boneInstance.unique:
				newVal = boneInstance.getUniquePropertyIndexValue(self.valuesCache, boneName)
				if newVal is not None:
					try:
						dbObj = db.Get(db.Key.from_path("%s_%s_uniquePropertyIndex" % (self.kindName, boneName), newVal))
						if dbObj["references"] != self["key"]: #This valus is taken (sadly, not by us)
							complete = False
							if isinstance(boneInstance.unique, unicode):
								errorMsg = _(boneInstance.unique)
							else:
								errorMsg = _("This value is not available")
							self.errors[boneName] = errorMsg
					except db.EntityNotFoundError:
						pass

		if( len(data) == 0
		    or (len(data) == 1 and "key" in data)
		    or ("nomissing" in data.keys() and str(data["nomissing"]) == "1" )):
			super(BaseSkeleton, self).__setattr__( "errors", {} )

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
				bone.refresh( self.valuesCache, key, self )


class MetaSkel(MetaBaseSkel):
	def __init__(cls, name, bases, dct):
		super(MetaSkel, cls).__init__(name, bases, dct)
		relNewFileName = inspect.getfile(cls).replace(os.getcwd(), "")

		# Automatic determination of the kindName, if the class is not part of the server.
		if (cls.kindName is __undefindedC__
		    and not relNewFileName.strip(os.path.sep).startswith("server")
		    and not "viur_doc_build" in dir(sys)):
			if cls.__name__.endswith("Skel"):
				cls.kindName = cls.__name__.lower()[:-4]
			else:
				cls.kindName = cls.__name__.lower()
		# Prevent duplicate definitions of skeletons
		if cls.kindName and cls.kindName is not __undefindedC__ and cls.kindName in MetaBaseSkel._skelCache.keys():
			relOldFileName = inspect.getfile(MetaBaseSkel._skelCache[cls.kindName]).replace(os.getcwd(), "")
			if relNewFileName.strip(os.path.sep).startswith("server"):
				# The currently processed skeleton is from the server.* package
				pass
			elif relOldFileName.strip(os.path.sep).startswith("server"):
				# The old one was from server - override it
				MetaBaseSkel._skelCache[cls.kindName] = cls
			else:
				raise ValueError("Duplicate definition for %s in %s and %s" %
				                 (cls.kindName, relNewFileName, relOldFileName))
		# Ensure that all skeletons are defined in /skeletons/
		relFileName = inspect.getfile(cls).replace(os.getcwd(), "")
		if (not relFileName.strip(os.path.sep).startswith("skeletons")
		    and not relFileName.strip(os.path.sep).startswith("server")
		    and not "viur_doc_build" in dir(sys)):  # Do not check while documentation build
			raise NotImplementedError("Skeletons must be defined in /skeletons/")
		if cls.kindName and cls.kindName is not __undefindedC__:
			MetaBaseSkel._skelCache[cls.kindName] = cls

class Skeleton(BaseSkeleton):
	__metaclass__ = MetaSkel

	kindName = __undefindedC__ # To which kind we save our data to
	searchIndex = None # If set, use this name as the index-name for the GAE search API
	subSkels = {} # List of pre-defined sub-skeletons of this type

	# The "key" bone stores the current database key of this skeleton.
	# Warning: Assigning to this bones value is dangerous and does *not* affect the actual key
	# its stored in
	key = baseBone(descr="key", readOnly=True, visible=False)

	# The date (including time) when this entry has been created
	creationdate = dateBone(descr="created at",
	                        readOnly=True, visible=False,
	                        creationMagic=True, indexed=True,
	                        localize=bool(pytz))

	# The last date (including time) when this entry has been updated
	changedate = dateBone(descr="updated at",
	                        readOnly=True, visible=False,
	                        updateMagic=True, indexed=True,
	                        localize=bool(pytz))

	def __init__(self, *args, **kwargs):
		super(Skeleton, self).__init__(*args, **kwargs)
		assert self.kindName and self.kindName is not __undefindedC__, "You must set kindName on this skeleton!"

	def all(self):
		"""
			Create a query with the current Skeletons kindName.

			:returns: A db.Query object which allows for entity filtering and sorting.
			:rtype: :class:`server.db.Query`
		"""
		return (db.Query(self.kindName, srcSkelClass=self))

	def fromDB(self, key):
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
		if isinstance(key, basestring):
			try:
				key = db.Key(key)
			except db.BadKeyError:
				key = unicode(key)
				if key.isdigit():
					key = long(key)
				elif not len(key):
					raise ValueError("fromDB called with empty key!")
				key = db.Key.from_path(self.kindName, key)
		if not isinstance(key, db.Key):
			raise ValueError(
				"fromDB expects an db.Key instance, an string-encoded key or a long as argument, got \"%s\" instead" % key)
		if key.kind() != self.kindName:  # Wrong Kind
			return (False)
		try:
			dbRes = db.Get(key)
		except db.EntityNotFoundError:
			return (False)
		if dbRes is None:
			return (False)
		self.setValues(dbRes)
		key = str(dbRes.key())
		self["key"] = key
		return (True)

	def toDB(self, clearUpdateTag=False):
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

		def txnUpdate(key, mergeFrom, clearUpdateTag):
			blobList = set()
			skel = type(mergeFrom)()
			# Load the current values from Datastore or create a new, empty db.Entity
			if not key:
				dbObj = db.Entity(skel.kindName)
				oldBlobLockObj = None
			else:
				k = db.Key(key)
				assert k.kind() == skel.kindName, "Cannot write to invalid kind!"
				try:
					dbObj = db.Get(k)
				except db.EntityNotFoundError:
					dbObj = db.Entity(k.kind(), id=k.id(), name=k.name(), parent=k.parent())
				else:
					skel.setValues(dbObj)
				try:
					oldBlobLockObj = db.Get(db.Key.from_path("viur-blob-locks", str(k)))
				except:
					oldBlobLockObj = None

			# Remember old hashes for bones that must have an unique value
			oldUniqeValues = {}
			for boneName, boneInstance in skel.items():
				if boneInstance.unique:
					if "%s.uniqueIndexValue" % boneName in dbObj.keys():
						oldUniqeValues[boneName] = dbObj["%s.uniqueIndexValue" % boneName]

			## Merge the values from mergeFrom in
			# for key, bone in skel.items():
			#	if key in mergeFrom.keys() and mergeFrom[ key ]:
			#		bone.mergeFrom( mergeFrom[ key ] )
			skel.setValuesCache(mergeFrom.getValuesCache())
			unindexed_properties = []
			for key, _bone in skel.items():
				tmpKeys = dbObj.keys()
				dbObj = _bone.serialize(mergeFrom.valuesCache, key, dbObj)
				newKeys = [x for x in dbObj.keys() if
				           not x in tmpKeys]  # These are the ones that the bone added
				if not _bone.indexed:
					unindexed_properties += newKeys
				blobList.update(_bone.getReferencedBlobs(self.valuesCache, key))

			if clearUpdateTag:
				dbObj["viur_delayed_update_tag"] = 0  # Mark this entity as Up-to-date.
			else:
				dbObj[
					"viur_delayed_update_tag"] = time()  # Mark this entity as dirty, so the background-task will catch it up and update its references.
			dbObj.set_unindexed_properties(unindexed_properties)
			dbObj = skel.preProcessSerializedData(dbObj)
			try:
				ourKey = str(dbObj.key())
			except:  # Its not an update but an insert, no key yet
				ourKey = None
			# Lock hashes from bones that must have unique values
			newUniqeValues = {}
			for boneName, boneInstance in skel.items():
				if boneInstance.unique:
					# Check if the property is really unique
					newUniqeValues[boneName] = boneInstance.getUniquePropertyIndexValue(
						self.valuesCache, boneName)
					if newUniqeValues[boneName] is not None:
						try:
							lockObj = db.Get(db.Key.from_path(
								"%s_%s_uniquePropertyIndex" % (skel.kindName, boneName),
								newUniqeValues[boneName]))
							if lockObj[
								"references"] != ourKey:  # This value has been claimed, and that not by us
								raise ValueError(
									"The value of property %s has been recently claimed!" % boneName)
						except db.EntityNotFoundError:  # No lockObj found for that value, we can use that
							pass
						dbObj["%s.uniqueIndexValue" % boneName] = newUniqeValues[boneName]
					else:
						if "%s.uniqueIndexValue" % boneName in dbObj.keys():
							del dbObj["%s.uniqueIndexValue" % boneName]
			if not skel.searchIndex:
				# We generate the searchindex using the full skel, not this (maybe incomplete one)
				tags = []
				for key, _bone in skel.items():
					if _bone.searchable:
						tags += [tag for tag in _bone.getSearchTags(self.valuesCache, key) if
						         (tag not in tags and len(tag) < 400)]
				dbObj["viur_tags"] = tags
			db.Put(dbObj)  # Write the core entry back
			# Now write the blob-lock object
			blobList = skel.preProcessBlobLocks(blobList)
			if blobList is None:
				raise ValueError(
					"Did you forget to return the bloblist somewhere inside getReferencedBlobs()?")
			if None in blobList:
				raise ValueError("None is not a valid blobKey.")
			if oldBlobLockObj is not None:
				oldBlobs = set(oldBlobLockObj["active_blob_references"] if oldBlobLockObj[
					                                                           "active_blob_references"] is not None else [])
				removedBlobs = oldBlobs - blobList
				oldBlobLockObj["active_blob_references"] = list(blobList)
				if oldBlobLockObj["old_blob_references"] is None:
					oldBlobLockObj["old_blob_references"] = [x for x in removedBlobs]
				else:
					tmp = set(oldBlobLockObj["old_blob_references"] + [x for x in removedBlobs])
					oldBlobLockObj["old_blob_references"] = [x for x in (tmp - blobList)]
				oldBlobLockObj["has_old_blob_references"] = oldBlobLockObj[
					                                            "old_blob_references"] is not None and len(
					oldBlobLockObj["old_blob_references"]) > 0
				oldBlobLockObj["is_stale"] = False
				db.Put(oldBlobLockObj)
			else:  # We need to create a new blob-lock-object
				blobLockObj = db.Entity("viur-blob-locks", name=str(dbObj.key()))
				blobLockObj["active_blob_references"] = list(blobList)
				blobLockObj["old_blob_references"] = []
				blobLockObj["has_old_blob_references"] = False
				blobLockObj["is_stale"] = False
				db.Put(blobLockObj)
			for boneName, boneInstance in skel.items():
				if boneInstance.unique:
					# Update/create/delete missing lock-objects
					if boneName in oldUniqeValues.keys() and oldUniqeValues[boneName] != \
						newUniqeValues[boneName]:
						# We had an old lock and its value changed
						try:
							# Try to delete the old lock
							oldLockObj = db.Get(db.Key.from_path(
								"%s_%s_uniquePropertyIndex" % (skel.kindName, boneName),
								oldUniqeValues[boneName]))
							if oldLockObj["references"] != ourKey:
								# We've been supposed to have that lock - but we don't.
								# Don't remove that lock as it now belongs to a different entry
								logging.critical(
									"Detected Database corruption! A Value-Lock had been reassigned!")
							else:
								# It's our lock which we don't need anymore
								db.Delete(db.Key.from_path(
									"%s_%s_uniquePropertyIndex" % (
									skel.kindName, boneName),
									oldUniqeValues[boneName]))
						except db.EntityNotFoundError as e:
							logging.critical(
								"Detected Database corruption! Could not delete stale lock-object!")
					if newUniqeValues[boneName] is not None:
						# Lock the new value
						newLockObj = db.Entity(
							"%s_%s_uniquePropertyIndex" % (skel.kindName, boneName),
							name=newUniqeValues[boneName])
						newLockObj["references"] = str(dbObj.key())
						db.Put(newLockObj)
			return (str(dbObj.key()), dbObj, skel)

		# END of txnUpdate subfunction

		key = self["key"] or None
		if not isinstance(clearUpdateTag, bool):
			raise ValueError(
				"Got an unsupported type %s for clearUpdateTag. toDB doesn't accept a key argument any more!" % str(
					type(clearUpdateTag)))

		# Allow bones to perform outstanding "magic" operations before saving to db
		for bkey, _bone in self.items():
			_bone.performMagic(self.valuesCache, bkey, isAdd=(key == None))

		# Run our SaveTxn
		if db.IsInTransaction():
			key, dbObj, skel = txnUpdate(key, self, clearUpdateTag)
		else:
			key, dbObj, skel = db.RunInTransactionOptions(db.TransactionOptions(xg=True),
			                                              txnUpdate, key, self, clearUpdateTag)

		# Perform post-save operations (postProcessSerializedData Hook, Searchindex, ..)
		self["key"] = str(key)
		if self.searchIndex:  # Add a Document to the index if an index specified
			fields = []

			for boneName, bone in skel.items():
				if bone.searchable:
					fields.extend(bone.getSearchDocumentFields(self.valuesCache, boneName))

			fields = skel.getSearchDocumentFields(fields)
			if fields:
				try:
					doc = search.Document(doc_id="s_" + str(key), fields=fields)
					search.Index(name=skel.searchIndex).put(doc)
				except:
					pass

			else:  # Remove the old document (if any)
				try:
					search.Index(name=self.searchIndex).remove("s_" + str(key))
				except:
					pass

		for boneName, bone in skel.items():
			bone.postSavedHandler(self.valuesCache, boneName, skel, key, dbObj)

		skel.postSavedHandler(key, dbObj)

		if not clearUpdateTag:
			updateRelations(key, time() + 1)

		return (key)

	def preProcessBlobLocks(self, locks):
		"""
			Can be overridden to modify the list of blobs referenced by this skeleton
		"""
		return (locks)

	def preProcessSerializedData(self, entity):
		"""
			Can be overridden to modify the :class:`server.db.Entity` before its actually
			written to the data store.
		"""
		return (entity)

	def getSearchDocumentFields(self, fields):
		"""
			Can be overridden to modify the list of search document fields before they are
			added to the index.
		"""
		return (fields)

	def postSavedHandler(self, key, dbObj):
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

	def delete(self):
		"""
			Deletes the entity associated with the current Skeleton from the data store.
		"""

		def txnDelete(key, skel):
			dbObj = db.Get(db.Key(key))  # Fetch the raw object as we might have to clear locks
			for boneName, bone in skel.items():
				# Ensure that we delete any value-lock objects remaining for this entry
				if bone.unique:
					try:
						logging.error("x1")
						logging.error(dbObj.keys())
						if "%s.uniqueIndexValue" % boneName in dbObj.keys():
							logging.error("x2")
							db.Delete(db.Key.from_path(
								"%s_%s_uniquePropertyIndex" % (skel.kindName, boneName),
								dbObj["%s.uniqueIndexValue" % boneName]))
					except db.EntityNotFoundError:
						raise
						pass
			# Delete the blob-key lock object
			try:
				lockObj = db.Get(db.Key.from_path("viur-blob-locks", str(key)))
			except:
				lockObj = None
			if lockObj is not None:
				if lockObj["old_blob_references"] is None and lockObj["active_blob_references"] is None:
					db.Delete(lockObj)  # Nothing to do here
				else:
					if lockObj["old_blob_references"] is None:
						# No old stale entries, move active_blob_references -> old_blob_references
						lockObj["old_blob_references"] = lockObj["active_blob_references"]
					elif lockObj["active_blob_references"] is not None:
						# Append the current references to the list of old & stale references
						lockObj["old_blob_references"] += lockObj["active_blob_references"]
					lockObj["active_blob_references"] = []  # There are no active ones left
					lockObj["is_stale"] = True
					lockObj["has_old_blob_references"] = True
					db.Put(lockObj)
			db.Delete(db.Key(key))

		key = self["key"]
		if key is None:
			raise ValueError("This skeleton is not in the database (anymore?)!")
		skel = type(self)()
		if not skel.fromDB(key):
			raise ValueError("This skeleton is not in the database (anymore?)!")
		db.RunInTransactionOptions(db.TransactionOptions(xg=True), txnDelete, key, skel)
		for boneName, _bone in skel.items():
			_bone.postDeletedHandler(skel, boneName, key)
		skel.postDeletedHandler(key)
		if self.searchIndex:
			try:
				search.Index(name=self.searchIndex).remove("s_" + str(key))
			except:
				pass
		self["key"] = None



class RelSkel(BaseSkeleton):
	"""
		This is a Skeleton-like class that acts as a container for Skeletons used as a
		additional information data skeleton for
		:class:`~server.bones.extendedRelationalBone.extendedRelationalBone`.

		It needs to be sub-classed where information about the kindName and its attributes
		(bones) are specified.

		The Skeleton stores its bones in an :class:`OrderedDict`-Instance, so the definition order of the
		contained bones remains constant.
	"""

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
		super(BaseSkeleton, self).__setattr__("errors", {})
		for key,_bone in self.items():
			if _bone.readOnly:
				continue
			error = _bone.fromClient( self.valuesCache, key, data )
			if isinstance( error, errors.ReadFromClientError ):
				self.errors.update( error.errors )
				if error.forceFail:
					complete = False
			else:
				self.errors[ key ] = error
			if error  and _bone.required:
				complete = False
		if( len( data )==0 or (len(data)==1 and "key" in data) or ("nomissing" in data.keys() and str(data["nomissing"])=="1") ):
			super(BaseSkeleton, self).__setattr__("errors", {})
		return( complete )

	def serialize(self):
		class FakeEntity(dict):
			def set(self, key, value, indexed=False):
				self[key] = value
		dbObj = FakeEntity()
		for key, _bone in self.items():
			dbObj = _bone.serialize( self.valuesCache, key, dbObj )
		if "key" in self.keys(): #Write the key seperatly, as the base-bone doesn't store it
			dbObj["key"] = self["key"]
		return dbObj

	def unserialize(self, values):
		"""
			Loads 'values' into this skeleton.

			:param values: Dict with values we'll assign to our bones
			:type values: dict | db.Entry
			:return:
		"""
		for bkey,_bone in self.items():
			if isinstance( _bone, baseBone ):
				if bkey=="key":
					try:
						# Reading the value from db.Entity
						self.valuesCache[bkey] = str( values.key() )
					except:
						# Is it in the dict?
						if "key" in values.keys():
							self.valuesCache[bkey] = str( values["key"] )
						else: #Ingore the key value
							pass
				else:
					_bone.unserialize( self.valuesCache, bkey, values )


class RefSkel(RelSkel):
	@classmethod
	def fromSkel(cls, skelCls, *args):
		"""
			Creates a relSkel from a skeleton-class using only the bones explicitly named
			in \*args

			:param skelCls: A class or instance of BaseSkel we'll adapt the model from
			:type skelCls: BaseSkeleton
			:param args: List of bone names we'll adapt
			:type args: list of str
			:return: A new instance of RefSkel
			:rtype: RefSkel
		"""
		skel = cls(cloned=True)
		# Remove the __isInitialized_ marker sothat we can write directly to __dataDict__ (which is a
		# safe operation in this case as RelSkels must not be subclassed and therefore cannot contain
		# class-level bones
		#super(BaseSkeleton, skel).__delattr__("_BaseSkeleton__isInitialized_")
		for key in args:
			if key in dir(skelCls):
				setattr(skel, key, getattr(skelCls, key))
				skel[key] = None
		#super(BaseSkeleton, skel).__setattr__("_BaseSkeleton__isInitialized_", True)
		return skel

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
		self.customQueryInfo = {}

	def __iter__(self):
		for cacheItem in super(SkelList, self).__iter__():
			self.baseSkel.setValuesCache(cacheItem)
			yield self.baseSkel

	def pop(self, index=None):
		item = super(SkelList, self).pop(index)
		self.baseSkel.setValuesCache(item)
		return self.baseSkel

### Tasks ###

@callDeferred
def updateRelations( destID, minChangeTime, cursor=None ):
	logging.debug("Starting updateRelations for %s ; minChangeTime %s", destID, minChangeTime)
	updateListQuery = db.Query( "viur-relations" ).filter("dest.key =", destID ).filter("viur_delayed_update_tag <",minChangeTime)
	if cursor:
		updateListQuery.cursor( cursor )
	updateList = updateListQuery.run(limit=5)

	for srcRel in updateList:
		try:
			skel = skeletonByKind(srcRel["viur_src_kind"])()
		except AssertionError:
			logging.info("Deleting %s which refers to unknown kind %s" % (str(srcRel.key()), srcRel["viur_src_kind"]))
			continue

		if not skel.fromDB( str(srcRel.key().parent()) ):
			logging.warning("Cannot update stale reference to %s (referenced from %s)" % (str(srcRel.key().parent()), str(srcRel.key())))
			continue
		for key,_bone in skel.items():
			_bone.refresh(skel.valuesCache, key, skel)
		skel.toDB( clearUpdateTag=True )
	if len(updateList)==5:
		updateRelations( destID, minChangeTime, updateListQuery.getCursor().urlsafe() )


@CallableTask
class TaskUpdateSearchIndex( CallableTaskBase ):
	"""
	This tasks loads and saves *every* entity of the given module.
	This ensures an updated searchIndex and verifies consistency of this data.
	"""
	key = "rebuildSearchIndex"
	name = u"Rebuild search index"
	descr = u"This task can be called to update search indexes and relational information."


	def canCall(self):
		"""
		Checks wherever the current user can execute this task
		:returns: bool
		"""
		user = utils.getCurrentUser()
		return user is not None and "root" in user["access"]

	def dataSkel(self):
		modules = ["*"] + listKnownSkeletons()
		skel = BaseSkeleton(cloned=True)
		skel.module = selectOneBone( descr="Module", values={ x: x for x in modules}, required=True )
		def verifyCompact(val):
			if not val or val.lower()=="no" or val=="YES":
				return None
			return "Must be \"No\" or uppercase \"YES\" (very dangerous!)"
		skel.compact = stringBone(descr="Recreate Entities", vfunc=verifyCompact, required=False, defaultValue="NO")
		return skel


	def execute(self, module, compact="", *args, **kwargs):
		usr = utils.getCurrentUser()
		if not usr:
			logging.warning("Don't know who to inform after rebuilding finished")
			notify = None
		else:
			notify = usr["name"]
		if module == "*":
			for module in listKnownSkeletons():
				logging.info("Rebuilding search index for module '%s'" % module)
				processChunk(module, compact, None,  notify=notify)
		else:
			processChunk(module, compact, None, notify=notify)

@callDeferred
def processChunk(module, compact, cursor, allCount=0, notify=None):
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
		processChunk(module, compact, newCursor.urlsafe(), allCount + count, notify)
	else:
		try:
			if notify:
				txt = ( "Subject: Rebuild search index finished for %s\n\n"+
			                "ViUR finished to rebuild the search index for module %s.\n"+
			                "%d records updated in total on this kind.") % (module, module, allCount)
				utils.sendEMail([notify], txt, None)
		except: #OverQuota, whatever
			pass
