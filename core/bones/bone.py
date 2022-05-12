# -*- coding: utf-8 -*-
from viur.core.config import conf
from viur.core import db
import logging
import hashlib
import copy
from enum import Enum
from dataclasses import dataclass, field
from typing import Union, Dict, List, Set, Any

__systemIsIntitialized_ = False


def setSystemInitialized():
	global __systemIsIntitialized_
	from viur.core.skeleton import iterAllSkelClasses, skeletonByKind
	__systemIsIntitialized_ = True
	for skelCls in iterAllSkelClasses():
		skelCls.setSystemInitialized()


def getSystemInitialized():
	global __systemIsIntitialized_
	return __systemIsIntitialized_


class ReadFromClientErrorSeverity(Enum):
	NotSet = 0
	InvalidatesOther = 1
	Empty = 2
	Invalid = 3


@dataclass
class ReadFromClientError:
	severity: ReadFromClientErrorSeverity
	errorMessage: str
	fieldPath: List[str] = field(default_factory=list)
	invalidatedFields: List[str] = None


class UniqueLockMethod(Enum):
	SameValue = 1  # Lock this value we have just one entry, or lock each value individually if bone is multiple
	SameSet = 2  # Same Set of entries (including duplicates), any order
	SameList = 3  # Same Set of entries (including duplicates), in this specific order


@dataclass
class UniqueValue:  # Mark a bone as unique (it must have a different value for each entry)
	method: UniqueLockMethod  # How to handle multiple values (for bones with multiple=True)
	lockEmpty: bool  # If False, empty values ("", 0) are not locked - needed if a field is unique but not required
	message: str  # Error-Message displayed to the user if the requested value is already taken


@dataclass
class MultipleConstraints:  # Used to define constraints on multiple bones
	minAmount: int = 0  # Lower bound of how many entries can be submitted
	maxAmount: int = 0  # Upper bound of how many entries can be submitted
	preventDuplicates: bool = False  # Prevent the same value of being used twice


class baseBone(object):  # One Bone:
	type = "hidden"
	isClonedInstance = False

	def __init__(
		self,
		*,
		defaultValue: Any = None,
		descr: str = "",
		getEmptyValueFunc: callable = None,
		indexed: bool = True,
		isEmptyFunc: callable = None,  # fixme: Rename this, see below.
		languages: Union[None, List[str]] = None,
		multiple: Union[bool, MultipleConstraints] = False,
		params: Dict = None,
		readOnly: bool = False,
		required: bool = False,
		searchable: bool = False,
		unique: Union[None, UniqueValue] = None,
		vfunc: callable = None,  # fixme: Rename this, see below.
		visible: bool = True,
	):
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
			:param searchable: If True, this bone will be included in the fulltext search. Can be used
				without the need of also been indexed.
			:type searchable: bool
			:param vfunc: If given, a callable validating the user-supplied value for this bone. This
				callable must return None if the value is valid, a String containing an meaningful
				error-message for the user otherwise.
			:type vfunc: callable
			:param readOnly: If True, the user is unable to change the value of this bone. If a value for
				this bone is given along the POST-Request during Add/Edit, this value will be ignored.
				Its still possible for the developer to modify this value by assigning skel.bone.value.
			:type readOnly: bool
			:param visible: If False, the value of this bone should be hidden from the user. This does *not*
				protect the value from beeing exposed in a template, nor from being transferred to the
				client (ie to the admin or as hidden-value in html-forms)
				Again: This is just a hint. It cannot be used as a security precaution.
			:type visible: bool

			.. NOTE::
				The kwarg 'multiple' is not supported by all bones

		"""
		self.isClonedInstance = getSystemInitialized()

		# Standard definitions
		self.descr = descr
		self.params = params or {}
		self.multiple = multiple
		self.required = required
		self.readOnly = readOnly
		self.searchable = searchable
		self.visible = visible
		self.indexed = indexed

		# Multi-language support
		if not (
			languages is None or
			(isinstance(languages, list) and len(languages) > 0
				and all([isinstance(x, str) for x in languages]))
		):
			raise ValueError("languages must be None or a list of strings")

		self.languages = languages

		# Default value
		# Convert a None default-value to the empty container that's expected if the bone is multiple or has languages
		if defaultValue is None and self.languages:
			self.defaultValue = {}
		elif defaultValue is None and self.multiple:
			self.defaultValue = []
		else:
			self.defaultValue = defaultValue

		# Unique values
		if unique:
			if not isinstance(unique, UniqueValue):
				raise ValueError("Unique must be an instance of UniqueValue")
			if not self.multiple and unique.method.value != 1:
				raise ValueError("'SameValue' is the only valid method on non-multiple bones")

		self.unique = unique

		# Override some validations and value functions by parameter instead of subclassing
		# todo: This can be done better and more straightforward.
		if vfunc:
			self.isInvalid = vfunc  # fixme: why is this called just vfunc, and not isInvalidValue/isInvalidValueFunc?

		if isEmptyFunc:
			self.isEmpty = isEmptyFunc  # fixme: why is this not called isEmptyValue/isEmptyValueFunc?

		if getEmptyValueFunc:
			self.getEmptyValue = getEmptyValueFunc

	def setSystemInitialized(self):
		"""
			Can be overridden to initialize properties that depend on the Skeleton system being initialized
		"""
		pass

	def isInvalid(self, value):
		"""
			Returns None if the value would be valid for
			this bone, an error-message otherwise.
		"""
		return False

	def isEmpty(self, rawValue: Any) -> bool:
		"""
			Check if the given single value represents the "empty" value.
			This usually is the empty string, 0 or False.

			Warning: isEmpty takes precedence over isInvalid! The empty value is always valid - unless the bone
				is required. But even then the empty value will be reflected back to the client.

			Warning: rawValue might be the string/object received from the user (untrusted input!) or the value
				returned by get

		"""
		return not bool(rawValue)

	def getDefaultValue(self, skeletonInstance):
		if callable(self.defaultValue):
			return self.defaultValue(skeletonInstance, self)
		elif isinstance(self.defaultValue, list):
			return self.defaultValue[:]
		elif isinstance(self.defaultValue, dict):
			return self.defaultValue.copy()
		else:
			return self.defaultValue

	def getEmptyValue(self) -> Any:
		"""
			Returns the value representing an empty field for this bone.
			This might be the empty string for str/text Bones, Zero for numeric bones etc.
		"""
		return None

	def __setattr__(self, key, value):
		if not self.isClonedInstance and getSystemInitialized() and key != "isClonedInstance" and not key.startswith(
			"_"):
			raise AttributeError("You cannot modify this Skeleton. Grab a copy using .clone() first")
		super(baseBone, self).__setattr__(key, value)

	def collectRawClientData(self, name, data, multiple, languages, collectSubfields):
		fieldSubmitted = False
		if languages:
			res = {}
			for lang in languages:
				if not collectSubfields:
					if "%s.%s" % (name, lang) in data:
						fieldSubmitted = True
						res[lang] = data["%s.%s" % (name, lang)]
						if multiple and not isinstance(res[lang], list):
							res[lang] = [res[lang]]
						elif not multiple and isinstance(res[lang], list):
							if res[lang]:
								res[lang] = res[lang][0]
							else:
								res[lang] = None
				else:
					for key in data.keys():  # Allow setting relations with using, multiple and languages back to none
						if key == "%s.%s" % (name, lang):
							fieldSubmitted = True
					prefix = "%s.%s." % (name, lang)
					if multiple:
						tmpDict = {}
						for key, value in data.items():
							if not key.startswith(prefix):
								continue
							fieldSubmitted = True
							partKey = key.replace(prefix, "")
							firstKey, remainingKey = partKey.split(".", maxsplit=1)
							try:
								firstKey = int(firstKey)
							except:
								continue
							if firstKey not in tmpDict:
								tmpDict[firstKey] = {}
							tmpDict[firstKey][remainingKey] = value
						tmpList = list(tmpDict.items())
						tmpList.sort(key=lambda x: x[0])
						res[lang] = [x[1] for x in tmpList]
					else:
						tmpDict = {}
						for key, value in data.items():
							if not key.startswith(prefix):
								continue
							fieldSubmitted = True
							partKey = key.replace(prefix, "")
							tmpDict[partKey] = value
						res[lang] = tmpDict
			return res, fieldSubmitted
		else:  # No multi-lang
			if not collectSubfields:
				if name not in data:  ## Empty!
					return None, False
				val = data[name]
				if multiple and not isinstance(val, list):
					return [val], True
				elif not multiple and isinstance(val, list):
					if val:
						return val[0], True
					else:
						return None, True  # Empty!
				else:
					return val, True
			else:  # No multi-lang but collect subfields
				for key in data.keys():  # Allow setting relations with using, multiple and languages back to none
					if key == name:
						fieldSubmitted = True
				prefix = "%s." % name
				if multiple:
					tmpDict = {}
					for key, value in data.items():
						if not key.startswith(prefix):
							continue
						fieldSubmitted = True
						partKey = key.replace(prefix, "")
						try:
							firstKey, remainingKey = partKey.split(".", maxsplit=1)
							firstKey = int(firstKey)
						except:
							continue
						if firstKey not in tmpDict:
							tmpDict[firstKey] = {}
						tmpDict[firstKey][remainingKey] = value
					tmpList = list(tmpDict.items())
					tmpList.sort(key=lambda x: x[0])
					return [x[1] for x in tmpList], fieldSubmitted
				else:
					res = {}
					for key, value in data.items():
						if not key.startswith(prefix):
							continue
						fieldSubmitted = True
						subKey = key.replace(prefix, "")
						res[subKey] = value
					return res, fieldSubmitted

	def parseSubfieldsFromClient(self) -> bool:
		"""
			Whenever this request should try to parse subfields submitted from the client.
			Set only to true if you expect a list of dicts to be transmitted
		"""
		return False

	def singleValueFromClient(self, value, skel, name, origData):
		# The baseBone will not read any data in fromClient. Use rawValueBone if needed.
		return self.getEmptyValue(), [
			ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Will not read a baseBone fromClient!")]

	def fromClient(self, skel: 'SkeletonInstance', name: str, data: dict) -> Union[None, List[ReadFromClientError]]:
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.

			:param name: Our name in the skeleton
			:type name: str
			:param data: User-supplied request-data
			:type data: dict
			:returns: None or str
		"""
		subFields = self.parseSubfieldsFromClient()
		parsedData, fieldSubmitted = self.collectRawClientData(name, data, self.multiple, self.languages, subFields)
		if not fieldSubmitted:
			return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, "Field not submitted")]
		errors = []
		isEmpty = True
		if self.languages and self.multiple:
			res = {}
			for language in self.languages:
				res[language] = []
				if language in parsedData:
					for singleValue in parsedData[language]:
						if self.isEmpty(singleValue):
							continue
						isEmpty = False
						parsedVal, parseErrors = self.singleValueFromClient(singleValue, skel, name, data)
						res[language].append(parsedVal)
						if parseErrors:
							errors.extend(parseErrors)
		elif self.languages:  # and not self.multiple is implicit - this would have been handled above
			res = {}
			for language in self.languages:
				res[language] = None
				if language in parsedData:
					if self.isEmpty(parsedData[language]):
						res[language] = self.getEmptyValue()
						continue
					isEmpty = False
					parsedVal, parseErrors = self.singleValueFromClient(parsedData[language], skel, name, data)
					res[language] = parsedVal
					if parseErrors:
						errors.extend(parseErrors)
		elif self.multiple:  # and not self.languages is implicit - this would have been handled above
			res = []
			for idx, singleValue in enumerate(parsedData):
				if self.isEmpty(singleValue):
					continue
				isEmpty = False
				parsedVal, parseErrors = self.singleValueFromClient(singleValue, skel, name, data)
				res.append(parsedVal)
				if parseErrors:
					for err in parseErrors:
						err.fieldPath.insert(0, str(idx))
					errors.extend(parseErrors)
		else:  # No Languages, not multiple
			if self.isEmpty(parsedData):
				res = self.getEmptyValue()
				isEmpty = True
			else:
				isEmpty = False
				res, parseErrors = self.singleValueFromClient(parsedData, skel, name, data)
				if parseErrors:
					errors.extend(parseErrors)
		skel[name] = res
		if isEmpty:
			return [ReadFromClientError(ReadFromClientErrorSeverity.Empty, "Field not set")]
		if self.multiple and isinstance(self.multiple, MultipleConstraints):
			errors.extend(self.validateMultipleConstraints(skel, name))
		return errors or None

	def validateMultipleConstraints(self, skel: 'SkeletonInstance', name: str) -> List[ReadFromClientError]:
		"""
			Validates our value against our multiple constrains.
			Returns a ReadFromClientError for each violation (eg. too many items and duplicates)
		"""
		res = []
		value = skel[name]
		constraints = self.multiple
		if constraints.minAmount and len(value) < constraints.minAmount:
			res.append(ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Too few items"))
		if constraints.maxAmount and len(value) > constraints.maxAmount:
			res.append(ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Too many items"))
		if constraints.preventDuplicates:
			if len(set(value)) != len(value):
				res.append(ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Duplicate items"))
		return res

	def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
		return value

	def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
		"""
			Serializes this bone into something we
			can write into the datastore.

			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:returns: dict
		"""
		if name in skel.accessedValues:
			newVal = skel.accessedValues[name]
			if self.languages and self.multiple:
				res = db.Entity()
				res["_viurLanguageWrapper_"] = True
				for language in self.languages:
					res[language] = []
					if not self.indexed:
						res.exclude_from_indexes.add(language)
					if language in newVal:
						for singleValue in newVal[language]:
							res[language].append(self.singleValueSerialize(singleValue, skel, name, parentIndexed))
			elif self.languages:
				res = db.Entity()
				res["_viurLanguageWrapper_"] = True
				for language in self.languages:
					res[language] = None
					if not self.indexed:
						res.exclude_from_indexes.add(language)
					if language in newVal:
						res[language] = self.singleValueSerialize(newVal[language], skel, name, parentIndexed)
			elif self.multiple:
				res = []

				assert newVal is None or isinstance(newVal, (list, tuple)), \
					f"Cannot handle {repr(newVal)} here. Expecting list or tuple."

				for singleValue in (newVal or ()):
					res.append(self.singleValueSerialize(singleValue, skel, name, parentIndexed))

			else:  # No Languages, not Multiple
				res = self.singleValueSerialize(newVal, skel, name, parentIndexed)
			skel.dbEntity[name] = res
			# Ensure our indexed flag is up2date
			indexed = self.indexed and parentIndexed
			if indexed and name in skel.dbEntity.exclude_from_indexes:
				skel.dbEntity.exclude_from_indexes.discard(name)
			elif not indexed and name not in skel.dbEntity.exclude_from_indexes:
				skel.dbEntity.exclude_from_indexes.add(name)
			return True
		return False

	def singleValueUnserialize(self, val):
		return val

	def unserialize(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> bool:
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.
			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:param expando: An instance of the dictionary-like db.Entity class
			:type expando: db.Entity
			:returns: bool
		"""
		if name in skel.dbEntity:
			loadVal = skel.dbEntity[name]
		elif conf.get("viur.viur2import.blobsource") and any([x.startswith("%s." % name) for x in skel.dbEntity.keys()]):
			# We're importing from an old ViUR2 instance - there may only be keys prefixed with our name
			loadVal = None
		else:
			skel.accessedValues[name] = self.getDefaultValue(skel)
			return False
		if self.languages and self.multiple:
			res = {}
			if isinstance(loadVal, dict) and "_viurLanguageWrapper_" in loadVal:
				for language in self.languages:
					res[language] = []
					if language in loadVal:
						tmpVal = loadVal[language]
						if not isinstance(tmpVal, list):
							tmpVal = [tmpVal]
						for singleValue in tmpVal:
							res[language].append(self.singleValueUnserialize(singleValue))
			else:  # We could not parse this, maybe it has been written before languages had been set?
				for language in self.languages:
					res[language] = []
				mainLang = self.languages[0]
				if loadVal is None:
					pass
				elif isinstance(loadVal, list):
					for singleValue in loadVal:
						res[mainLang].append(self.singleValueUnserialize(singleValue))
				else:  # Hopefully it's a value stored before languages and multiple has been set
					res[mainLang].append(self.singleValueUnserialize(loadVal))
		elif self.languages:
			res = {}
			if isinstance(loadVal, dict) and "_viurLanguageWrapper_" in loadVal:
				for language in self.languages:
					res[language] = None
					if language in loadVal:
						tmpVal = loadVal[language]
						if isinstance(tmpVal, list) and tmpVal:
							tmpVal = tmpVal[0]
						res[language] = self.singleValueUnserialize(tmpVal)
			else:  # We could not parse this, maybe it has been written before languages had been set?
				for language in self.languages:
					res[language] = None
					oldKey = "%s.%s" % (name, language)
					if oldKey in skel.dbEntity and skel.dbEntity[oldKey]:
						res[language] = self.singleValueUnserialize(skel.dbEntity[oldKey])
						loadVal = None  # Don't try to import later again, this format takes precedence
				mainLang = self.languages[0]
				if loadVal is None:
					pass
				elif isinstance(loadVal, list) and loadVal:
					res[mainLang] = self.singleValueUnserialize(loadVal)
				else:  # Hopefully it's a value stored before languages and multiple has been set
					res[mainLang] = self.singleValueUnserialize(loadVal)
		elif self.multiple:
			res = []
			if isinstance(loadVal, dict) and "_viurLanguageWrapper_" in loadVal:
				# Pick one language we'll use
				if conf["viur.defaultLanguage"] in loadVal:
					loadVal = loadVal[conf["viur.defaultLanguage"]]
				else:
					loadVal = [x for x in loadVal.values() if x is not True]
			if loadVal and not isinstance(loadVal, list):
				loadVal = [loadVal]
			if loadVal:
				for val in loadVal:
					res.append(self.singleValueUnserialize(val))
		else:  # Not multiple, no languages
			res = None
			if isinstance(loadVal, dict) and "_viurLanguageWrapper_" in loadVal:
				# Pick one language we'll use
				if conf["viur.defaultLanguage"] in loadVal:
					loadVal = loadVal[conf["viur.defaultLanguage"]]
				else:
					loadVal = [x for x in loadVal.values() if x is not True]
			if loadVal and isinstance(loadVal, list):
				loadVal = loadVal[0]
			if loadVal is not None:
				res = self.singleValueUnserialize(loadVal)
		skel.accessedValues[name] = res
		return True

	def delete(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str):
		"""
			Like postDeletedHandler, but runs inside the transaction
		:param skel:
		:param name:
		:return:
		"""
		pass

	def buildDBFilter(self, name, skel, dbFilter, rawFilter, prefix=None):
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
		myKeys = [key for key in rawFilter.keys() if (key == name or key.startswith(name + "$"))]

		if len(myKeys) == 0:
			return dbFilter

		for key in myKeys:
			value = rawFilter[key]
			tmpdata = key.split("$")

			if len(tmpdata) > 1:
				if isinstance(value, list):
					continue
				if tmpdata[1] == "lt":
					dbFilter.filter((prefix or "") + tmpdata[0] + " <", value)
				elif tmpdata[1] == "le":
					dbFilter.filter((prefix or "") + tmpdata[0] + " <=", value)
				elif tmpdata[1] == "gt":
					dbFilter.filter((prefix or "") + tmpdata[0] + " >", value)
				elif tmpdata[1] == "ge":
					dbFilter.filter((prefix or "") + tmpdata[0] + " >=", value)
				elif tmpdata[1] == "lk":
					dbFilter.filter((prefix or "") + tmpdata[0] + " =", value)
				else:
					dbFilter.filter((prefix or "") + tmpdata[0] + " =", value)
			else:
				if isinstance(value, list):
					dbFilter.filter((prefix or "") + key + " IN", value)
				else:
					dbFilter.filter((prefix or "") + key + " =", value)

		return dbFilter

	def buildDBSort(self, name, skel, dbFilter, rawFilter):
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
			if "orderdir" in rawFilter and rawFilter["orderdir"] == "1":
				order = (rawFilter["orderby"], db.SortOrder.Descending)
			elif "orderdir" in rawFilter and rawFilter["orderdir"] == "2":
				order = (rawFilter["orderby"], db.SortOrder.InvertedAscending)
			elif "orderdir" in rawFilter and rawFilter["orderdir"] == "3":
				order = (rawFilter["orderby"], db.SortOrder.InvertedDescending)
			else:
				order = (rawFilter["orderby"], db.SortOrder.Ascending)
			queries = dbFilter.queries
			if queries is None:
				return  # This query is unsatisfiable
			elif isinstance(queries, db.QueryDefinition):
				inEqFilter = [x for x in queries.filters.keys() if
							  (">" in x[-3:] or "<" in x[-3:] or "!=" in x[-4:])]
			elif isinstance(queries, list):
				inEqFilter = None
				for singeFilter in queries:
					newInEqFilter = [x for x in singeFilter.filters.keys() if
									 (">" in x[-3:] or "<" in x[-3:] or "!=" in x[-4:])]
					if inEqFilter and newInEqFilter and inEqFilter != newInEqFilter:
						raise NotImplementedError("Impossible ordering!")
					inEqFilter = newInEqFilter
			if inEqFilter:
				inEqFilter = inEqFilter[0][: inEqFilter[0].find(" ")]
				if inEqFilter != order[0]:
					logging.warning("I fixed you query! Impossible ordering changed to %s, %s" % (inEqFilter, order[0]))
					dbFilter.order((inEqFilter, order))
				else:
					dbFilter.order(order)
			else:
				dbFilter.order(order)
		return dbFilter

	def _hashValueForUniquePropertyIndex(self, value: Union[str, int]) -> List[str]:
		def hashValue(value: Union[str, int]) -> str:
			h = hashlib.sha256()
			h.update(str(value).encode("UTF-8"))
			res = h.hexdigest()
			if isinstance(value, int) or isinstance(value, float):
				return "I-%s" % res
			elif isinstance(value, str):
				return "S-%s" % res
			elif isinstance(value, db.Key):
				# We Hash the keys here by our self instead of relying on str() or to_legacy_urlsafe()
				# as these may change in the future, which would invalidate all existing locks
				def keyHash(key):
					if key is None:
						return "-"
					return "%s-%s-<%s>" % (hashValue(key.kind), hashValue(key.id_or_name), keyHash(key.parent))
				return "K-%s" % keyHash(value)
			raise NotImplementedError("Type %s can't be safely used in an uniquePropertyIndex" % type(value))

		if not value and not self.unique.lockEmpty:
			return []  # We are zero/empty string and these should not be locked
		if not self.multiple:
			return [hashValue(value)]
		# We have an multiple bone here
		if not isinstance(value, list):
			value = [value]
		tmpList = [hashValue(x) for x in value]
		if self.unique.method == UniqueLockMethod.SameValue:
			# We should lock each entry individually; lock each value
			return tmpList
		elif self.unique.method == UniqueLockMethod.SameSet:
			# We should ignore the sort-order; so simply sort that List
			tmpList.sort()
		# Lock the value for that specific list
		return [hashValue(", ".join(tmpList))]

	def getUniquePropertyIndexValues(self, skel, name: str) -> List[str]:
		"""
			Returns a list of hashes for our current value(s), used to store in the uniquePropertyValue index.
		"""
		val = skel[name]
		if val is None:
			return []
		return self._hashValueForUniquePropertyIndex(val)

	def getReferencedBlobs(self, skel, name):
		"""
			Returns the list of blob keys referenced from this bone
		"""
		return []

	def performMagic(self, valuesCache, name, isAdd):
		"""
			This function applies "magically" functionality which f.e. inserts the current Date or the current user.
			:param isAdd: Signals whereever this is an add or edit operation.
			:type isAdd: bool
		"""
		pass  # We do nothing by default

	def postSavedHandler(self, skel, boneName, key):
		"""
			Can be overridden to perform further actions after the main entity has been written.

			:param boneName: Name of this bone
			:type boneName: str

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
			:type boneName: str
			:param key: The old Database Key of the entity we've deleted
			:type key: str
		"""
		pass

	def refresh(self, skel, boneName) -> None:
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
			logging.error("Ignoring values from conflicting boneType (%s is not a instance of %s)!" % (
				getattr(otherSkel, boneName), type(self)))
			return
		valuesCache[boneName] = copy.deepcopy(otherSkel.valuesCache.get(boneName, None))

	def setBoneValue(self, skel: 'SkeletonInstance', boneName: str, value: Any, append: bool,
					 language: Union[None, str] = None) -> bool:
		"""
			Set our value to 'value'.
			Santy-Checks are performed; if the value is invalid, no modification will happen.

			:param skel: Dictionary with the current values from the skeleton we belong to
			:param boneName: The Bone which should be modified
			:param value: The value that should be assigned. It's type depends on the type of that bone
			:param append: If true, the given value is appended to the values of that bone instead of
				replacing it. Only supported on bones with multiple=True
			:param language: Set/append which language
			:return: Wherever that operation succeeded or not.

		"""
		assert not (bool(self.languages) ^ bool(language)), "Language is required or not supported"
		assert not append or self.multiple, "Can't append - bone is not multiple"

		if not append and self.multiple:
			# set multiple values at once
			val = []
			errors = []
			for singleValue in value:
				singleValue, singleError = self.singleValueFromClient(singleValue, skel, boneName, {boneName: value})
				val.append(singleValue)
				if singleError:
					errors.extend(singleError)
		else:
			# set or append one value
			val, errors = self.singleValueFromClient(value, skel, boneName, {boneName: value})

		if errors:
			for e in errors:
				if e.severity in [ReadFromClientErrorSeverity.Invalid, ReadFromClientErrorSeverity.NotSet]:
					# If an invalid datatype (or a non-parseable structure) have been passed, abort the store
					return False
		if not append and not language:
			skel[boneName] = val
		elif append and language:
			if not language in skel[boneName] or not isinstance(skel[boneName][language], list):
				skel[boneName][language] = []
			skel[boneName][language].append(val)
		elif append:
			if not isinstance(skel[boneName], list):
				skel[boneName] = []
			skel[boneName].append(val)
		else:  # Just language
			skel[boneName][language] = val
		return True

	def getSearchTags(self, skeletonInstance, name: str) -> Set[str]:
		return set()
