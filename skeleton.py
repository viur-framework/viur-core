# -*- coding: utf-8 -*-
from __future__ import annotations
from viur.core import db, utils, conf, errors
from viur.core.bones import baseBone, keyBone, dateBone, selectBone, relationalBone, stringBone
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.tasks import CallableTask, CallableTaskBase, callDeferred
from collections import OrderedDict
from time import time
import inspect, os, sys, logging, copy
from typing import Union, Dict, List, Callable

try:
	import pytz
except:
	pytz = None

__undefindedC__ = object()


class MetaBaseSkel(type):
	"""
		This is the meta class for Skeletons.
		It is used to enforce several restrictions on bone names, etc.
	"""
	_skelCache = {}  # Mapping kindName -> SkelCls
	_allSkelClasses = set()  # list of all known skeleton classes (including Ref and Mail-Skels)

	__reservedKeywords_ = {"self", "cursor", "amount", "orderby", "orderdir",
						   "style", "items", "keys", "values"}

	def __init__(cls, name, bases, dct):
		boneMap = {}
		for key in dir(cls):
			prop = getattr(cls, key)
			if isinstance(prop, baseBone):
				if "." in key:
					raise AttributeError("Invalid bone '%s': Bone keys may not contain a dot (.)" % key)
				if key in MetaBaseSkel.__reservedKeywords_:
					raise AttributeError("Invalid bone '%s': Bone cannot have any of the following names: %s" %
										 (key, str(MetaBaseSkel.__reservedKeywords_)))

				boneMap[key] = prop
		cls.__boneMap__ = boneMap
		MetaBaseSkel._allSkelClasses.add(cls)
		super(MetaBaseSkel, cls).__init__(name, bases, dct)


def skeletonByKind(kindName):
	if not kindName:
		return None

	assert kindName in MetaBaseSkel._skelCache, "Unknown skeleton '%s'" % kindName
	return MetaBaseSkel._skelCache[kindName]


def listKnownSkeletons():
	return list(MetaBaseSkel._skelCache.keys())[:]


def iterAllSkelClasses():
	for cls in MetaBaseSkel._allSkelClasses:
		yield cls


class SkeletonValues(object):
	__slots__ = ["entity", "accessedValues", "renderAccessedValues"]

	def __init__(self, entity=None):
		self.entity = entity
		self.accessedValues = {}
		self.renderAccessedValues = {}


class BaseSkeleton(object, metaclass=MetaBaseSkel):
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
	boneMap = None

	def items(self):
		yield from self.boneMap.items()

	def keys(self):
		yield from self.boneMap.keys()

	def values(self):
		yield from self.boneMap.values()

	def __contains__(self, item):
		return item in self.boneMap

	def __setattr__(self, key, value):
		if key in {"errors", "valuesCache", "isClonedInstance", "renderPreparation", "boneMap"}:
			super(BaseSkeleton, self).__setattr__(key, value)
		elif (value is None and key in self.boneMap) or isinstance(value, baseBone):
			if not value:
				del self.boneMap[key]
			else:
				self.boneMap[key] = value
		else:
			raise ValueError("Invalid access to skeleton-instance")

	# if "_BaseSkeleton__isInitialized_" in dir(self):
	#	if not key in {"errors", "valuesCache", "isClonedInstance",
	#				   "renderPreparation"} and not self.isClonedInstance:
	#		raise AttributeError(
	#			"You cannot directly modify the skeleton instance. Grab a copy using .clone() first!")
	# super(BaseSkeleton, self).__setattr__(key, value)
	# if isinstance(value, baseBone):
	#	self.__boneNames__ = self.__boneNames__ + [key]

	def __delattr__(self, key):
		del self.boneMap[key]

	# if "_BaseSkeleton__isInitialized_" in dir(self) and not self.isClonedInstance:
	#	raise AttributeError("You cannot directly modify the skeleton instance. Grab a copy using .clone() first!")
	# super(BaseSkeleton, self).__delattr__(key)
	# if key in self.__boneNames__:
	#	self.__boneNames__ = [x for x in self.__boneNames__ if x != key]

	def __getattribute__(self, key):
		boneMap = super().__getattribute__("boneMap")
		if boneMap and key in boneMap:
			return boneMap[key]
		prop = super().__getattribute__(key)
		if not isinstance(prop, baseBone):
			return prop
		raise ValueError("Unknown bone %s" % key)

	@classmethod
	def subSkel(cls, *args, fullClone=False, **kwargs):
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
		if not args:
			raise ValueError("Which subSkel?")
		return cls(subSkelNames=args, fullClone=fullClone)


	def __init__(self, subSkelNames: Union[None, List[str]] = None, fullClone: bool = False, *args, **kwargs):
		"""
			Initializes a Skeleton.

			:param kindName: If set, it overrides the kindName of the current class.
			:type kindName: str
		"""
		super().__init__()
		self.errors = []
		self.valuesCache: SkeletonValues = SkeletonValues()
		self.renderPreparation = None
		if not subSkelNames and not fullClone:
			self.boneMap = self.__boneMap__.copy()
		elif not subSkelNames and fullClone:
			self.boneMap = {}
			for k, v in self.__boneMap__.items():
				v = copy.deepcopy(v)
				v.isClonedInstance = True
				self.boneMap[k] = v
		else:  # We're building a subskel
			self.boneMap = {}
			boneList = set(self.subSkels["*"]) if "*" in self.subSkels else set()
			for subSkelName in subSkelNames:
				if not subSkelName in self.subSkels:
					raise ValueError("Unknown sub-skeleton %s for skel %s" % (subSkelName, self.kindName))
				boneList.update(self.subSkels[subSkelName])
				#boneList.extend(skel.subSkels[name][:])
			for boneKey, bone in self.__boneMap__.items():
				if boneKey in boneList or any([boneKey.startswith(x[:-1]) for x in boneList if x[-1]=="*"]):
					if fullClone:
						bone = copy.deepcopy(bone)
						bone.isClonedInstance = True
					self.boneMap[boneKey] = bone



	def setValuesCache(self, cache):
		self.valuesCache = cache

	def getValuesCache(self):
		return self.valuesCache

	@classmethod
	def setSystemInitialized(cls):
		for attrName in dir(cls):
			bone = getattr(cls, attrName)
			if isinstance(bone, baseBone):
				bone.setSystemInitialized()

	def clone(self):
		"""
			Creates a stand-alone copy of the current Skeleton object.

			:returns: The stand-alone copy of the object.
			:rtype: Skeleton
		"""
		cpy = copy.deepcopy(self)
		cpy.isClonedInstance = True
		for key, bone in cpy.items():
			bone.isClonedInstance = True
		return cpy

	def shallowClone(self):
		skel = type(self)()
		skel.errors = self.errors
		skel.valuesCache = self.valuesCache
		skel.boneMap = self.boneMap
		skel.renderPreparation = self.renderPreparation
		return skel

	"""
	def ensureIsCloned(self):
		" ""
			Ensure that we are a instance that can be modified.
			If we are, just self is returned (it's a no-op), otherwise
			we'll return a cloned copy.

			:return: A copy from self or just self itself
			:rtype: BaseSkeleton
		" ""
		if self.isClonedInstance:
			return self
		else:
			return self.clone()
	"""

	def __setitem__(self, key, value):
		assert self.renderPreparation is None, "Cannot modify values while rendering"
		if isinstance(value, baseBone):
			raise AttributeError("Don't assign this bone object as skel[\"%s\"] = ... anymore to the skeleton. "
								 "Use skel.%s = ... for bone to skeleton assignment!" % (key, key))
		# elif isinstance(value, db.Key):
		#	value = str(value[1])
		self.valuesCache.accessedValues[key] = value

	def __getitem__(self, key):
		vc = self.valuesCache
		if self.renderPreparation:
			if key in vc.renderAccessedValues:
				return vc.renderAccessedValues[key]
		if key not in vc.accessedValues:
			boneInstance = getattr(self, key, None)
			if boneInstance:
				if vc.entity is not None:
					boneInstance.unserialize(vc, key)
				else:
					vc.accessedValues[key] = boneInstance.getDefaultValue()
		if not self.renderPreparation:
			return vc.accessedValues.get(key)
		value = self.renderPreparation(getattr(self, key), self, key, vc.accessedValues.get(key))
		vc.renderAccessedValues[key] = value
		return value

	def __delitem__(self, key):
		raise NotImplementedError  # FIXME: Does delitem still make sense?
		if key in self.valuesCache.accessedValues:
			del self.valuesCache.accessedValues[key]
		if key in self.valuesCache.entity:
			del self.valuesCache.entity[key]

	def setValues(self, values):
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
		"""
		self.valuesCache = SkeletonValues(entity=values)
		if isinstance(values, db.Entity):
			self["key"] = values.key
		return

	def getValues(self):
		"""
			Returns the current bones of the Skeleton as a dictionary.

			:returns: Dictionary, where the keys are the bones and the values the current values.
			:rtype: dict
		"""
		return {k: self[k] for k in self.boneMap.keys()}


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
		self[boneName]  # FIXME, ensure this bone is unserialized first
		return bone.setBoneValue(self.valuesCache.accessedValues, boneName, value, append)

	def fromClient(self, data):
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
		self.errors = []

		for key, _bone in self.items():
			if _bone.readOnly:
				continue
			errors = _bone.fromClient(self.valuesCache.accessedValues, key, data)
			if errors:
				self.errors.extend(errors)
				for error in errors:
					if error.severity == ReadFromClientErrorSeverity.Empty and _bone.required \
							or error.severity == ReadFromClientErrorSeverity.Invalid:
						complete = False
		# FIXME!
		# if (len(data) == 0
		#		or (len(data) == 1 and "key" in data)
		#		or ("nomissing" in data and str(data["nomissing"]) == "1")):
		#	super(BaseSkeleton, self).__setattr__("errors", {})

		return complete

	def refresh(self):
		"""
			Refresh the bones current content.

			This function causes a refresh of all relational bones and their associated
			information.
		"""
		for key, bone in self.items():
			if not isinstance(bone, baseBone):
				continue
			self[key]  # Ensure value gets loaded
			if "refresh" in dir(bone):
				bone.refresh(self.valuesCache, key, self)


class MetaSkel(MetaBaseSkel):
	def __init__(cls, name, bases, dct):
		super(MetaSkel, cls).__init__(name, bases, dct)
		relNewFileName = inspect.getfile(cls).replace(os.getcwd(), "")

		# Check if we have an abstract skeleton
		if cls.__name__.endswith("AbstractSkel"):
			# Ensure that it doesn't have a kindName
			assert cls.kindName is __undefindedC__ or cls.kindName is None, "Abstract Skeletons can't have a kindName"
			# Prevent any further processing by this class; it has to be sub-classed before it can be used
			return

		# Automatic determination of the kindName, if the class is not part of the server.
		if (cls.kindName is __undefindedC__
				and not relNewFileName.strip(os.path.sep).startswith("viur")
				and not "viur_doc_build" in dir(sys)):
			if cls.__name__.endswith("Skel"):
				cls.kindName = cls.__name__.lower()[:-4]
			else:
				cls.kindName = cls.__name__.lower()
		# Try to determine which skeleton definition takes precedence
		if cls.kindName and cls.kindName is not __undefindedC__ and cls.kindName in MetaBaseSkel._skelCache:
			relOldFileName = inspect.getfile(MetaBaseSkel._skelCache[cls.kindName]).replace(os.getcwd(), "")
			idxOld = min(
				[x for (x, y) in enumerate(conf["viur.skeleton.searchPath"]) if relOldFileName.startswith(y)] + [999])
			idxNew = min(
				[x for (x, y) in enumerate(conf["viur.skeleton.searchPath"]) if relNewFileName.startswith(y)] + [999])
			if idxNew == 999:
				# We could not determine a priority for this class as its from a path not listed in the config
				raise NotImplementedError(
					"Skeletons must be defined in a folder listed in conf[\"viur.skeleton.searchPath\"]")
			elif idxOld < idxNew:  # Lower index takes precedence
				# The currently processed skeleton has a lower priority than the one we already saw - just ignore it
				return
			elif idxOld > idxNew:
				# The currently processed skeleton has a higher priority, use that from now
				MetaBaseSkel._skelCache[cls.kindName] = cls
			else:  # They seem to be from the same Package - raise as something is messed up
				raise ValueError("Duplicate definition for %s in %s and %s" %
								 (cls.kindName, relNewFileName, relOldFileName))
		# Ensure that all skeletons are defined in folders listed in conf["viur.skeleton.searchPath"]
		if (not any([relNewFileName.startswith(x) for x in conf["viur.skeleton.searchPath"]])
				and not "viur_doc_build" in dir(sys)):  # Do not check while documentation build
			raise NotImplementedError(
				"Skeletons must be defined in a folder listed in conf[\"viur.skeleton.searchPath\"]")
		if cls.kindName and cls.kindName is not __undefindedC__:
			MetaBaseSkel._skelCache[cls.kindName] = cls


class CustomDatabaseAdapter:
	# Set to True if we can run a fulltext search using this database
	providesFulltextSearch: bool = False
	# Are results returned by `meth:fulltextSearch` guaranteed to also match the databaseQuery
	fulltextSearchGuaranteesQueryConstrains = False
	# Indicate that we can run more types of queries than originally supported by firestore
	providesCustomQueries: bool = False

	def preprocessEntry(self, entry: db.Entity, skel: BaseSkeleton, changeList: List[str], isAdd: bool) -> db.Entity:
		"""
		Can be overridden to add or alter the data of this entry before it's written to firestore.
		Will always be called inside an transaction.
		:param entry: The entry containing the serialized data of that skeleton
		:param skel: The (complete) skeleton this skel.toDB() runs for
		:param changeList: List of boneNames that are changed by this skel.toDB() call
		:param isAdd: Is this an update or an add?
		:return: The (maybe modified) entity
		"""
		return entry

	def updateEntry(self, dbObj: db.Entity, skel: BaseSkeleton, changeList: List[str], isAdd: bool) -> None:
		"""
		Like `meth:preprocessEntry`, but runs after the transaction had completed.
		Changes made to dbObj will be ignored.
		:param entry: The entry containing the serialized data of that skeleton
		:param skel: The (complete) skeleton this skel.toDB() runs for
		:param changeList: List of boneNames that are changed by this skel.toDB() call
		:param isAdd: Is this an update or an add?
		"""
		return

	def deleteEntry(self, entry: db.Entity, skel: BaseSkeleton) -> None:
		"""
		Called, after an skeleton has been successfully deleted from firestore
		:param entry: The db.Entity object containing an snapshot of the data that has been deleted
		:param skel: The (complete) skeleton for which `meth:delete' had been called
		"""
		return

	def fulltextSearch(self, queryString: str, databaseQuery: db.Query) -> List[db.Entity]:
		"""
		If this database supports fulltext searches, this method has to implement them.
		If it's a plain fulltext search engine, leave 'prop:fulltextSearchGuaranteesQueryConstrains' set to False,
		then the server will post-process the list of entries returned from this function and drop any entry that
		cannot be returned due to other constrains set in 'param:databaseQuery'. If you can obey *every* constrain
		set in that Query, we can skip this post-processing and save some CPU-cycles.
		:param queryString: the string as received from the user (no quotation or other safety checks applied!)
		:param databaseQuery: The query containing any constrains that returned entries must also match
		:return:
		"""
		raise NotImplementedError


class Skeleton(BaseSkeleton, metaclass=MetaSkel):
	kindName: str = __undefindedC__  # To which kind we save our data to
	customDatabaseAdapter: Union[CustomDatabaseAdapter, None] = None
	subSkels = {}  # List of pre-defined sub-skeletons of this type
	interBoneValidations: List[
		Callable[[Skeleton], List[ReadFromClientError]]] = []  # List of functions checking inter-bone dependencies

	# The "key" bone stores the current database key of this skeleton.
	# Warning: Assigning to this bones value now *will* set the key
	# it gets stored in. Must be kept readOnly to avoid security-issues with add/edit.
	key = keyBone(descr="key", readOnly=True, visible=False)

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

	viurCurrentSeoKeys = stringBone(descr="Seo-Keys",
									readOnly=True,
									visible=False,
									languages=conf["viur.availableLanguages"])

	def __repr__(self):
		return "<skeleton %s with data=%r>" % (self.kindName, {k: self[k] for k in self.keys()})

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

	def fromClient(self, data):
		"""

		:param data:
		:return:
		"""
		# Load data into this skeleton
		complete = super(Skeleton, self).fromClient(data)

		# Check if all unique values are available
		for boneName, boneInstance in self.items():
			if boneInstance.unique:
				lockValues = boneInstance.getUniquePropertyIndexValues(self, boneName)
				for lockValue in lockValues:
					dbObj = db.Get(db.Key("%s_%s_uniquePropertyIndex" % (self.kindName, boneName), lockValue))
					if dbObj and (not self["key"] or dbObj["references"] != self["key"].id_or_name):
						# This value is taken (sadly, not by us)
						complete = False
						errorMsg = boneInstance.unique.message
						self.errors.append(ReadFromClientError(ReadFromClientErrorSeverity.Invalid, boneName, errorMsg))

		# Check inter-Bone dependencies
		for checkFunc in self.interBoneValidations:
			errors = checkFunc(self)
			if errors:
				for err in errors:
					if err.severity.value > 1:
						complete = False
				self.errors.extend(errors)

		return complete

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
		try:
			dbKey = db.keyHelper(key, self.kindName)
		except ValueError:  # This key did not parse
			return False
		dbRes = db.Get(dbKey)
		if dbRes is None:
			return False
		self.setValues(dbRes)
		# key = str(dbRes.key())
		self["key"] = dbKey
		return True

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

		def txnUpdate(dbKey, mergeFrom, clearUpdateTag):
			blobList = set()
			skel = type(mergeFrom)()
			changeList = []

			# Load the current values from Datastore or create a new, empty db.Entity
			if not dbKey:
				# We'll generate the key we'll be stored under early so we can use it for locks etc
				newKey = db.__client__.allocate_ids(db.Key(skel.kindName), 1)[0]
				dbObj = db.Entity(newKey)
				oldCopy = {}
				dbObj["viur"] = {}
				skel.valuesCache.entity = dbObj
				oldBlobLockObj = None
				isAdd = True
			else:
				if isinstance(dbKey, str) or isinstance(dbKey, int):
					dbKey = db.Key(self.kindName, dbKey)
				dbObj = db.Get(dbKey)
				if not dbObj:
					dbObj = db.Entity(dbKey)
					oldCopy = {}
					skel.valuesCache.entity = dbObj
				else:
					skel.setValues(dbObj)
					oldCopy = {k: v for k, v in dbObj.items()}
				oldBlobLockObj = db.Get(db.Key("viur-blob-locks", dbKey.id_or_name))
				isAdd = False
			if not "viur" in dbObj:
				dbObj["viur"] = {}
			# Merge values and assemble unique properties
			# Move accessed Values from srcSkel over to skel
			skel.valuesCache.accessedValues = mergeFrom.valuesCache.accessedValues
			for key, bone in skel.items():
				# Remember old hashes for bones that must have an unique value
				oldUniqueValues = []
				if bone.unique:
					if "%s_uniqueIndexValue" % key in dbObj["viur"]:
						oldUniqueValues = dbObj["viur"]["%s_uniqueIndexValue" % key]

				# Merge the values from mergeFrom in
				if key in skel.valuesCache.accessedValues:
					# bone.mergeFrom(skel.valuesCache, key, mergeFrom)
					bone.serialize(skel.valuesCache, key)

				## Serialize bone into entity
				# dbObj = bone.serialize(skel.valuesCache, key, dbObj)

				# Obtain referenced blobs
				blobList.update(bone.getReferencedBlobs(skel, key))

				# Check if the value has actually changed
				if dbObj.get(key) != oldCopy.get(key):
					changeList.append(key)

				# Lock hashes from bones that must have unique values
				if bone.unique:
					# Check if the property is really unique
					newUniqueValues = bone.getUniquePropertyIndexValues(skel, key)
					for newLockValue in newUniqueValues:
						lockObj = db.Get(db.Key("%s_%s_uniquePropertyIndex" % (skel.kindName, key), newLockValue))
						if lockObj:
							# There's already a lock for that value, check if we hold it
							if lockObj["references"] != dbObj.key.id_or_name:
								# This value has already been claimed, and not by us
								raise ValueError(
									"The unique value '%s' of bone '%s' has been recently claimed!" %
									(self[key], key))
						else:
							# This value is locked for the first time, create a new lock-object
							newLockObj = db.Entity(db.Key(
								"%s_%s_uniquePropertyIndex" % (skel.kindName, key),
								newLockValue))
							newLockObj["references"] = dbObj.key.id_or_name
							db.Put(newLockObj)
						if newLockValue in oldUniqueValues:
							oldUniqueValues.remove(newLockValue)
					dbObj["viur"]["%s_uniqueIndexValue" % key] = newUniqueValues
					# Remove any lock-object we're holding for values that we don't have anymore
					for oldValue in oldUniqueValues:
						# Try to delete the old lock
						oldLockObj = db.Get(("%s_%s_uniquePropertyIndex" % (skel.kindName, key), oldValue))
						if oldLockObj:
							if oldLockObj["references"] != dbObj.id_or_name:
								# We've been supposed to have that lock - but we don't.
								# Don't remove that lock as it now belongs to a different entry
								logging.critical("Detected Database corruption! A Value-Lock had been reassigned!")
							else:
								# It's our lock which we don't need anymore
								db.Delete(("%s_%s_uniquePropertyIndex" % (skel.kindName, key), oldValue))
						else:
							logging.critical("Detected Database corruption! Could not delete stale lock-object!")

			# Ensure the SEO-Keys are up2date
			lastRequestedSeoKeys = dbObj["viur"].get("viurLastRequestedSeoKeys") or {}
			lastSetSeoKeys = dbObj["viur"].get("viurCurrentSeoKeys") or {}
			currentSeoKeys = skel.getCurrentSEOKeys()
			if not isinstance(dbObj["viur"].get("viurCurrentSeoKeys"), dict):
				dbObj["viur"]["viurCurrentSeoKeys"] = {}
			if currentSeoKeys:
				# Convert to lower-case and remove certain characters
				for lang, value in list(currentSeoKeys.items()):
					value = value.lower()
					value = value.replace("<", "") \
						.replace(">", "") \
						.replace("\"", "") \
						.replace("'", "") \
						.replace("\n", "") \
						.replace("\0", "") \
						.replace("/", "") \
						.replace("\\", "") \
						.replace("?", "") \
						.replace("&", "") \
						.replace("#", "").strip()
					currentSeoKeys[lang] = value
			for language in (conf["viur.availableLanguages"] or [conf["viur.defaultLanguage"]]):
				if currentSeoKeys and language in currentSeoKeys:
					currentKey = currentSeoKeys[language]
					if currentKey != lastRequestedSeoKeys.get(language):  # This one is new or has changed
						newSeoKey = currentSeoKeys[language]
						for _ in range(0, 3):
							entryUsingKey = db.Query(self.kindName).filter("viurActiveSeoKeys AC", newSeoKey).get()
							if entryUsingKey and entryUsingKey.name != dbObj.name:
								# It's not unique; append a random string and try again
								newSeoKey = "%s-%s" % (currentSeoKeys[language], utils.generateRandomString(5).lower())
							else:
								break
						else:
							raise ValueError("Could not generate an unique seo key in 3 attempts")
					else:
						newSeoKey = currentKey
					lastSetSeoKeys[language] = newSeoKey
				else:
					# We'll use the database-key instead
					lastSetSeoKeys[language] = dbObj.key.id_or_name
				# Store the current, active key for that language
				dbObj["viur"]["viurCurrentSeoKeys"][language] = lastSetSeoKeys[language]
			if not dbObj["viur"].get("viurActiveSeoKeys"):
				dbObj["viur"]["viurActiveSeoKeys"] = []
			for language, seoKey in lastSetSeoKeys.items():
				if dbObj["viur"]["viurCurrentSeoKeys"][language] not in dbObj["viur"]["viurActiveSeoKeys"]:
					# Ensure the current, active seo key is in the list of all seo keys
					dbObj["viur"]["viurActiveSeoKeys"].insert(0, seoKey)
			if dbObj.key.id_or_name not in dbObj["viur"]["viurActiveSeoKeys"]:
				# Ensure that key is also in there
				dbObj["viur"]["viurActiveSeoKeys"].insert(0, str(dbObj.key.id_or_name))
			# Trim to the last 200 used entries
			dbObj["viur"]["viurActiveSeoKeys"] = dbObj["viur"]["viurActiveSeoKeys"][:200]
			# Store lastRequestedKeys so further updates can run more efficient
			dbObj["viur"]["viurLastRequestedSeoKeys"] = currentSeoKeys

			if clearUpdateTag:
				# Mark this entity as Up-to-date.
				dbObj["viur"]["delayedUpdateTag"] = 0
			else:
				# Mark this entity as dirty, so the background-task will catch it up and update its references.
				dbObj["viur"]["delayedUpdateTag"] = time()
			dbObj = skel.preProcessSerializedData(dbObj)

			# Allow the custom DB Adapter to apply last minute changes to the object
			if self.customDatabaseAdapter:
				dbObj = self.customDatabaseAdapter.preprocessEntry(dbObj, skel, changeList, isAdd)

			# Write the core entry back
			db.Put(dbObj)

			# Now write the blob-lock object
			blobList = skel.preProcessBlobLocks(blobList)
			if blobList is None:
				raise ValueError("Did you forget to return the bloblist somewhere inside getReferencedBlobs()?")
			if None in blobList:
				logging.error("b1l is %s" % blobList)
				raise ValueError("None is not a valid blobKey.")
			if oldBlobLockObj is not None:
				oldBlobs = set(oldBlobLockObj.get("active_blob_references") or [])
				removedBlobs = oldBlobs - blobList
				oldBlobLockObj["active_blob_references"] = list(blobList)
				if oldBlobLockObj["old_blob_references"] is None:
					oldBlobLockObj["old_blob_references"] = [x for x in removedBlobs]
				else:
					tmp = set(oldBlobLockObj["old_blob_references"] + [x for x in removedBlobs])
					oldBlobLockObj["old_blob_references"] = [x for x in (tmp - blobList)]
				oldBlobLockObj["has_old_blob_references"] = \
					oldBlobLockObj["old_blob_references"] is not None \
					and len(oldBlobLockObj["old_blob_references"]) > 0
				oldBlobLockObj["is_stale"] = False
				db.Put(oldBlobLockObj)
			else:  # We need to create a new blob-lock-object
				blobLockObj = db.Entity(db.Key("viur-blob-locks", dbObj.key.id_or_name))
				blobLockObj["active_blob_references"] = list(blobList)
				blobLockObj["old_blob_references"] = []
				blobLockObj["has_old_blob_references"] = False
				blobLockObj["is_stale"] = False
				db.Put(blobLockObj)

			return dbObj.key, dbObj, skel, changeList

		# END of txnUpdate subfunction

		key = self["key"] or None
		isAdd = key is None
		if not isinstance(clearUpdateTag, bool):
			raise ValueError(
				"Got an unsupported type %s for clearUpdateTag. toDB doesn't accept a key argument any more!" % str(
					type(clearUpdateTag)))

		# Allow bones to perform outstanding "magic" operations before saving to db
		for bkey, _bone in self.items():
			_bone.performMagic(self.valuesCache, bkey, isAdd=isAdd)

		# Run our SaveTxn
		if db.IsInTransaction():
			key, dbObj, skel, changeList = txnUpdate(key, self, clearUpdateTag)
		else:
			key, dbObj, skel, changeList = db.RunInTransaction(txnUpdate, key, self, clearUpdateTag)

		# Perform post-save operations (postProcessSerializedData Hook, Searchindex, ..)
		self["key"] = key

		for boneName, bone in skel.items():
			bone.postSavedHandler(skel, boneName, key)

		skel.postSavedHandler(key, dbObj)

		if not clearUpdateTag and not isAdd:
			updateRelations(key.to_legacy_urlsafe().decode("ASCII"), time() + 1, changeList if len(changeList) < 30 else None)

		# Inform the custom DB Adapter of the changes made to the entry
		if self.customDatabaseAdapter:
			self.customDatabaseAdapter.updateEntry(dbObj, skel, changeList, isAdd)

		return key

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

	def getCurrentSEOKeys(self) -> Union[None, Dict[str, str]]:
		"""
		Should be overridden to return a dictionary of language -> SEO-Friendly key
		this entry should be reachable under. How theses names are derived are entirely up to the application.
		If the name is already in use for this module, the server will automatically append some random string
		to make it unique.
		:return:
		"""
		return

	def delete(self):
		"""
			Deletes the entity associated with the current Skeleton from the data store.
		"""

		def txnDelete(key: str, skel: Skeleton):
			skelKey = (self.kindName, key)
			dbObj = db.Get(skelKey)  # Fetch the raw object as we might have to clear locks
			if dbObj.get("viur_incomming_relational_locks"):
				raise errors.Locked("This entry is locked!")
			for boneName, bone in skel.items():
				# Ensure that we delete any value-lock objects remaining for this entry
				if bone.unique:
					try:
						if "%s_uniqueIndexValue" % boneName in dbObj:
							db.Delete((
								"%s_%s_uniquePropertyIndex" % (skel.kindName, boneName),
								dbObj["%s_uniqueIndexValue" % boneName]))

					except db.EntityNotFoundError:
						raise
						pass
			# Delete the blob-key lock object
			lockObjectKey = ("viur-blob-locks", str(key))
			try:
				lockObj = db.Get(lockObjectKey)
			except:
				lockObj = None
			if lockObj is not None:
				if lockObj["old_blob_references"] is None and lockObj["active_blob_references"] is None:
					db.Delete(lockObjectKey)  # Nothing to do here
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
			db.Delete(skelKey)
			processRemovedRelations(skelKey)
			return dbObj

		key = self["key"]
		if key is None:
			raise ValueError("This skeleton is not in the database (anymore?)!")
		skel = type(self)()
		if not skel.fromDB(key):
			raise ValueError("This skeleton is not in the database (anymore?)!")
		if db.IsInTransaction():
			dbObj = txnDelete(key, skel)
		else:
			dbObj = db.RunInTransaction(txnDelete, key, skel)
		for boneName, _bone in skel.items():
			_bone.postDeletedHandler(skel, boneName, key)
		skel.postDeletedHandler(key)

		# Inform the custom DB Adapter
		if self.customDatabaseAdapter:
			self.customDatabaseAdapter.deleteEntry(dbObj, skel)


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

	def fromClient(self, data):
		"""
			Reads the data supplied by data.
			Unlike setValues, error-checking is performed.
			The values might be in a different representation than the one used in getValues/serValues.
			Even if this function returns False, all bones are guranteed to be in a valid state:
			The ones which have been read correctly contain their data; the other ones are set back to a safe default (None in most cases)
			So its possible to call save() afterwards even if reading data fromClient faild (through this might violates the assumed consitency-model!).

			:param data: Dictionary from which the data is read
			:type data: dict
			:returns: True if the data was successfully read; False otherwise (eg. some required fields where missing or invalid)
		"""
		complete = True
		super(BaseSkeleton, self).__setattr__("errors", [])
		for key, _bone in self.items():
			if _bone.readOnly:
				continue
			errors = _bone.fromClient(self.valuesCache["changedValues"], key, data)
			if errors:
				self.errors.extend(errors)
				for err in errors:
					if err.severity == ReadFromClientErrorSeverity.Empty and _bone.required \
							or err.severity == ReadFromClientErrorSeverity.Invalid:
						complete = False
		if (len(data) == 0 or (len(data) == 1 and "key" in data) or (
				"nomissing" in data and str(data["nomissing"]) == "1")):
			super(BaseSkeleton, self).__setattr__("errors", [])
		return complete

	def serialize(self):
		for key, _bone in self.items():
			if key in self.valuesCache.accessedValues:
				_bone.serialize(self.valuesCache, key,)
		# if "key" in self:  # Write the key seperatly, as the base-bone doesn't store it
		#	dbObj["key"] = self["key"]
		# FIXME: is this a good idea? Any other way to ensure only bones present in refKeys are serialized?
		return self.valuesCache.entity
		#return {k: v for k, v in self.valuesCache.entity.items() if k in self.__boneNames__}

	def unserialize(self, values):
		"""
			Loads 'values' into this skeleton.

			:param values: dict with values we'll assign to our bones
			:type values: dict | db.Entry
			:return:
		"""
		self.valuesCache = SkeletonValues(values)
		#self.valuesCache = {"entity": values, "changedValues": {}, "cachedRenderValues": {}}
		return
		for bkey, _bone in self.items():
			if isinstance(_bone, baseBone):
				if bkey == "key":
					try:
						# Reading the value from db.Entity
						self.valuesCache[bkey] = str(values.key())
					except:
						# Is it in the dict?
						if "key" in values:
							self.valuesCache[bkey] = str(values["key"])
						else:  # Ingore the key value
							pass
				else:
					_bone.unserialize(self.valuesCache, bkey, values)


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
		# super(BaseSkeleton, skel).__delattr__("_BaseSkeleton__isInitialized_")
		srcSkel = skelCls()
		skel.boneMap = {k:getattr(srcSkel, k) for k in srcSkel.keys() if k in args}
		#skel.__boneNames__ = []
		#for key, bone in srcSkel.items():
		#	if key in args:
		#		setattr(skel, key, bone)
		#		skel.__boneNames__.append(key)
		## skel[key] = None
		#skel.__boneNames__ = tuple(skel.__boneNames__)
		# super(BaseSkeleton, skel).__setattr__("_BaseSkeleton__isInitialized_", True)
		return skel


class SkelList(list):
	"""
		This class is used to hold multiple skeletons together with other, commonly used information.

		SkelLists are returned by Skel().all()...fetch()-constructs and provide additional information
		about the data base query, for fetching additional entries.

		:ivar cursor: Holds the cursor within a query.
		:vartype cursor: str
	"""

	__slots__ = ["baseSkel", "getCursor", "customQueryInfo", "renderPreparation"]

	def __init__(self, baseSkel):
		"""
			:param baseSkel: The baseclass for all entries in this list
		"""
		super(SkelList, self).__init__()
		self.baseSkel = baseSkel
		self.getCursor = lambda: None
		self.renderPreparation = None
		self.customQueryInfo = {}

	def __iter__(self):
		for cacheItem in super(SkelList, self).__iter__():
			self.baseSkel.setValuesCache(cacheItem)
			self.baseSkel.renderPreparation = self.renderPreparation
			yield self.baseSkel

	def pop(self, index=None):
		item = super(SkelList, self).pop(index)
		self.baseSkel.setValuesCache(item)
		self.baseSkel.renderPreparation = self.renderPreparation
		return self.baseSkel


### Tasks ###

@callDeferred
def processRemovedRelations(removedKey, cursor=None):
	kind, name = removedKey

	updateListQuery = db.Query("viur-relations").filter("dest.key =", name) \
		.filter("viur_dest_kind =", kind).filter("viur_relational_consistency >", 2)
	updateListQuery = updateListQuery.setCursor(cursor)
	updateList = updateListQuery.run(limit=5)
	for entry in updateList:
		skel = skeletonByKind(entry["viur_src_kind"])()
		assert skel.fromDB(entry["src"]["key"])
		if entry["viur_relational_consistency"] == 3:  # Set Null
			for key, _bone in skel.items():
				if isinstance(_bone, relationalBone):
					relVal = skel[key]
					if isinstance(relVal, dict) and relVal["dest"]["entity"]["key"] == name:
						# FIXME: Should never happen: "key" not in relVal["dest"]
						# skel.setBoneValue(key, None)
						skel[key] = None
					elif isinstance(relVal, list):
						skel[key] = [x for x in relVal if x["dest"]["key"] != name]
					else:
						print("Type? %s" % type(relVal))
			skel.toDB(clearUpdateTag=True)
		else:
			logging.critical("Cascading Delete to %s/%s" % (skel.kindName, skel["key"]))
			skel.delete()
			pass


@callDeferred
def updateRelations(destID, minChangeTime, changeList, cursor=None):
	logging.error("Updaterelations currently disabled")
	return
	logging.debug("Starting updateRelations for %s ; minChangeTime %s, Changelist: %s", destID, minChangeTime,
				  changeList)
	updateListQuery = db.Query("viur-relations").filter("dest.key =", destID) \
		.filter("viur_delayed_update_tag <", minChangeTime).filter("viur_relational_updateLevel =", 0)
	if changeList:
		updateListQuery.filter("viur_foreign_keys IA", changeList)
	if cursor:
		updateListQuery.cursor(cursor)
	updateList = updateListQuery.run(limit=5)

	def updateTxn(skel, key, srcRelKey):
		if not skel.fromDB(key):
			logging.warning("Cannot update stale reference to %s (referenced from %s)" % (key, srcRelKey))
			return
		for key, _bone in skel.items():
			_bone.refresh(skel.valuesCache, key, skel)
		skel.toDB(clearUpdateTag=True)

	for srcRel in updateList:
		try:
			skel = skeletonByKind(srcRel["viur_src_kind"])()
		except AssertionError:
			logging.info("Deleting %s which refers to unknown kind %s" % (str(srcRel.key()), srcRel["viur_src_kind"]))
			continue
		db.RunInTransaction(updateTxn, skel, srcRel["src"]["key"], srcRel.name)

	if len(updateList) == 5:
		updateRelations(destID, minChangeTime, changeList, updateListQuery.getCursor().urlsafe())


@CallableTask
class TaskUpdateSearchIndex(CallableTaskBase):
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
		skel.module = selectBone(descr="Module", values={x: x for x in modules}, required=True)

		def verifyCompact(val):
			if not val or val.lower() == "no" or val == "YES":
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
				processChunk(module, compact, None, notify=notify)
		else:
			processChunk(module, compact, None, notify=notify)


@callDeferred
def processChunk(module, compact, cursor, allCount=0, notify=None):
	"""
		Processes 100 Entries and calls the next batch
	"""
	Skel = skeletonByKind(module)
	if not Skel:
		logging.error("TaskUpdateSearchIndex: Invalid module")
		return
	query = Skel().all().setCursor(cursor)
	count = 0
	for obj in query.run(25):
		count += 1
		try:
			skel = Skel()
			skel.fromDB(obj.key)
			if compact == "YES":
				raise NotImplementedError()  # FIXME: This deletes the __currentKey__ property..
				skel.delete()
			skel.refresh()
			skel.toDB(clearUpdateTag=True)
		except Exception as e:
			logging.error("Updating %s failed" % str(obj.key))
			logging.exception(e)
			raise
	newCursor = query.getCursor()
	if not newCursor:  # We're done
		return
	newCursor = newCursor.decode("ASCII")
	logging.info("END processChunk %s, %d records refreshed" % (module, count))
	if count and newCursor and newCursor != cursor:
		# Start processing of the next chunk
		processChunk(module, compact, newCursor, allCount + count, notify)
	else:
		try:
			if notify:
				txt = ("Subject: Rebuild search index finished for %s\n\n" +
					   "ViUR finished to rebuild the search index for module %s.\n" +
					   "%d records updated in total on this kind.") % (module, module, allCount)
				utils.sendEMail([notify], txt, None)
		except:  # OverQuota, whatever
			pass


### Vacuum Relations

@CallableTask
class TaskVacuumRelations(CallableTaskBase):
	"""
	Checks entries in viur-relations and verifies that the src-kind and it's relational-bone still exists.
	"""
	key = "vacuumRelations"
	name = u"Vacuum viur-relations (dangerous)"
	descr = u"Drop stale inbound relations for the given kind"

	def canCall(self):
		"""
		Checks wherever the current user can execute this task
		:returns: bool
		"""
		user = utils.getCurrentUser()
		return user is not None and "root" in user["access"]

	def dataSkel(self):
		skel = BaseSkeleton(cloned=True)
		skel.module = stringBone(descr="Module", required=True)
		return skel

	def execute(self, module, *args, **kwargs):
		usr = utils.getCurrentUser()
		if not usr:
			logging.warning("Don't know who to inform after rebuilding finished")
			notify = None
		else:
			notify = usr["name"]
		processVacuumRelationsChunk(module.strip(), None, notify=notify)


@callDeferred
def processVacuumRelationsChunk(module, cursor, allCount=0, removedCount=0, notify=None):
	"""
		Processes 100 Entries and calls the next batch
	"""
	query = db.Query("viur-relations")
	if module != "*":
		query.filter("viur_src_kind =", module)
	query.cursor(cursor)
	countTotal = 0
	countRemoved = 0
	for relationObject in query.run(25):
		countTotal += 1
		srcKind = relationObject.get("viur_src_kind")
		if not srcKind:
			logging.critical("We got an relation-object without a srcKind!")
			continue
		srcProp = relationObject.get("viur_src_property")
		if not srcProp:
			logging.critical("We got an relation-object without a srcProp!")
			continue
		try:
			skel = skeletonByKind(srcKind)()
		except AssertionError:
			# The referenced skeleton does not exist in this data model -> drop that relation object
			logging.info("Deleting %r which refers to unknown kind %s", str(relationObject.key()), srcKind)
			db.Delete(relationObject)
			countRemoved += 1
			continue
		if srcProp not in skel:
			logging.info("Deleting %r which refers to non-existing relationalBone %s of %s",
						 str(relationObject.key()), srcProp, srcKind)
			db.Delete(relationObject)
			countRemoved += 1
	newCursor = query.getCursor()
	newTotalCount = allCount + countTotal
	newRemovedCount = removedCount + countRemoved
	logging.info("END processVacuumRelationsChunk %s, %d records processed, %s removed " % (
		module, newTotalCount, newRemovedCount))
	if countTotal and newCursor and newCursor.urlsafe() != cursor:
		# Start processing of the next chunk
		processVacuumRelationsChunk(module, newCursor.urlsafe(), newTotalCount, newRemovedCount, notify)
	else:
		try:
			if notify:
				txt = ("Subject: Vaccum Relations finished for %s\n\n" +
					   "ViUR finished to vaccum viur-relations.\n" +
					   "%d records processed, %d entries removed") % (module, newTotalCount, newRemovedCount)
				utils.sendEMail([notify], txt, None)
		except:  # OverQuota, whatever
			pass
