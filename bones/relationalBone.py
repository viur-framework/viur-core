# -*- coding: utf-8 -*-
from viur.core.bones import baseBone
from viur.core.bones.bone import getSystemInitialized
from viur.core.bones.stringBone import LanguageWrapper
from viur.core import db
from viur.core.errors import ReadFromClientError
from typing import List, Union

try:
	import extjson
except ImportError:
	# FIXME: That json will not read datetime objects
	import json as extjson
from time import time
from datetime import datetime
import logging
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
from typing import List
from enum import Enum
from itertools import chain


class RelationalConsistency(Enum):
	Ignore = 1  # Ignore stale relations (old behaviour)
	PreventDeletion = 2  # Lock target object so it cannot be deleted
	SetNull = 3  # Drop Relation if target object is deleted
	CascadeDeletion = 4  # Delete this object also if the referenced entry is deleted (Dangerous!)


class relationalBone(baseBone):
	"""
		This is our magic class implementing relations.

		This implementation is read-efficient, e.g. filtering by relational-properties only costs an additional
		small-op for each entity returned.
		However, it costs several more write-ops for writing an entity to the db.
		(These costs are somewhat around additional (4+len(refKeys)+len(parentKeys)) write-ops for each referenced
		property) for multiple=True relationalBones and (4+len(refKeys)) for n:1 relations)

		So don't use this if you expect data being read less frequently than written! (Sorry, we don't have a
		write-efficient method yet)
		To speedup writes to (maybe) referenced entities, information in these relations isn't updated instantly.
		Once a skeleton is updated, a deferred task is kicked off which updates the references to
		that skeleton (if any).
		As a result, you might see stale data until this task has been finished.

		Example:

			* Entity A references Entity B.
			* Both have a property "name".
			* Entity B gets updated (it name changes).
			* As "A" has a copy of entity "B"s values, you'll see "B"s old name inside the values of the
			  relationalBone when fetching entity A.

		If you filter a list by relational properties, this will also use the old data! (Eg. filtering A's list by
		B's new name won't return any result)
	"""
	refKeys = ["key", "name"]
	parentKeys = ["key", "name"]
	type = "relational"
	kind = None

	def __init__(self, kind=None, module=None, refKeys=None, parentKeys=None, multiple=False, format="$(dest.name)",
				 using=None, updateLevel=0, consistency=RelationalConsistency.Ignore, *args, **kwargs):
		"""
			Initialize a new relationalBone.

			:param kind: KindName of the referenced property.
			:type kind: str
			:param module: Name of the module which should be used to select entities of kind "type". If not set,
				the value of "type" will be used (the kindName must match the moduleName)
			:type type: str
			:param refKeys: A list of properties to include from the referenced property. These properties will be
				available in the template without having to fetch the referenced property. Filtering is also only possible
				by properties named here!
			:type refKeys: list of str
			:param parentKeys: A list of properties from the current skeleton to include. If mixing filtering by
				relational properties and properties of the class itself, these must be named here.
			:type parentKeys: list of str
			:param multiple: If True, allow referencing multiple Elements of the given class. (Eg. n:n-relation.
				otherwise its n:1 )
			:type multiple: False
			:param format: Hint for the admin how to display such an relation. See admin/utils.py:formatString for
				more information
			:type format: str
			:type format: String
			:param updateLevel: level 0==always update refkeys (old behavior), 1==update refKeys only on
				rebuildSearchIndex, 2==update only if explicitly set
			:type updateLevel: int
		"""
		baseBone.__init__(self, *args, **kwargs)
		self.multiple = multiple
		self.format = format
		# self._dbValue = None #Store the original result fetched from the db here so we have that information in case a referenced entity has been deleted

		if kind:
			self.kind = kind

		if module:
			self.module = module
		elif self.kind:
			self.module = self.kind

		if self.kind is None or self.module is None:
			raise NotImplementedError("Type and Module of relationalbone's must not be None")

		if refKeys:
			if not "key" in refKeys:
				raise AttributeError("'key' must be included in refKeys!")
			self.refKeys = refKeys

		if parentKeys:
			if not "key" in parentKeys:
				raise AttributeError("'key' must be included in parentKeys!")
			self.parentKeys = parentKeys

		self.using = using
		self.updateLevel = updateLevel
		self.consistency = consistency

		if getSystemInitialized():
			from viur.core.skeleton import RefSkel, SkeletonInstance
			self._refSkelCache = RefSkel.fromSkel(self.kind, *self.refKeys)
			self._skeletonInstanceClassRef = SkeletonInstance
		#	self._usingSkelCache = using() if using else None
		#else:
		#	self._refSkelCache = None
		#	self._usingSkelCache = None

	def setSystemInitialized(self):
		super(relationalBone, self).setSystemInitialized()
		from viur.core.skeleton import RefSkel, SkeletonInstance
		self._refSkelCache = RefSkel.fromSkel(self.kind, *self.refKeys)
		self._skeletonInstanceClassRef = SkeletonInstance
		#from viur.core.skeleton import RefSkel, skeletonByKind
		#self._refSkelCache = RefSkel.fromSkel(skeletonByKind(self.kind), *self.refKeys)
		#self._usingSkelCache = self.using() if self.using else None

	def _getSkels(self):
		refSkel = self._refSkelCache()
		usingSkel = self.using() if self.using else None
		return refSkel, usingSkel

	def singleValueUnserialize(self, val, skel: 'viur.core.skeleton.SkeletonInstance', name: str):
		"""
			Restores one of our values (including the Rel- and Using-Skel) from the serialized data read from the datastore
			:param value: Json-Encoded datastore property
			:return: Our Value (with restored RelSkel and using-Skel)
		"""
		if isinstance(val, str):
			try:
				value = extjson.loads(val)
			except:
				value = None
		else:
			value = val
		if value is None:
			return None
		assert isinstance(value, dict), "Read something from the datastore thats not a dict: %s" % str(type(value))
		if "dest" not in value:
			return None
		relSkel, usingSkel = self._getSkels()
		relSkel.unserialize(value["dest"])
		if self.using is not None:
			usingSkel.unserialize(value["rel"] or db.Entity())
			usingData = usingSkel
		else:
			usingData = None
		return {"dest": relSkel, "rel": usingData}


	def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
		oldRelationalLocks = set(skel.dbEntity.get("%s_outgoingRelationalLocks" % name) or [])
		newRelationalLocks = set()
		# Clean old properties from entry (prevent name collision)
		for k in list(skel.dbEntity.keys()):
			if k.startswith("%s." % name):
				del skel.dbEntity[k]
		indexed = self.indexed and parentIndexed
		if name not in skel.accessedValues:
			return
		elif not skel.accessedValues[name]:
			res = None
		elif self.languages and self.multiple:
			res = {"_viurLanguageWrapper_": True}
			newVals = skel.accessedValues[name]
			for language in self.languages:
				res[language] = []
				if language in newVals:
					for val in newVals[language]:
						if val["dest"]:
							refData = val["dest"].serialize(parentIndexed=indexed)
							newRelationalLocks.add(val["dest"]["key"])
						else:
							refData = None
						if val["rel"]:
							usingData = val["rel"].serialize(parentIndexed=indexed)
						else:
							usingData = None
						r = {"rel": usingData, "dest": refData}
						res[language].append(r)
		elif self.languages:
			res = {"_viurLanguageWrapper_": True}
			newVals = skel.accessedValues[name]
			for language in self.languages:
				res[language] = []
				if language in newVals:
					val = newVals[language]
					if val and val["dest"]:
						refData = val["dest"].serialize(parentIndexed=indexed)
						newRelationalLocks.add(val["dest"]["key"])
						if val["rel"]:
							usingData = val["rel"].serialize(parentIndexed=indexed)
						else:
							usingData = None
						r = {"rel": usingData, "dest": refData}
						res[language] = r
					else:
						res[language] = None
		elif self.multiple:
			res = []
			for val in skel.accessedValues[name]:
				if val["dest"]:
					refData = val["dest"].serialize(parentIndexed=indexed)
					newRelationalLocks.add(val["dest"]["key"])
				else:
					refData = None
				if val["rel"]:
					usingData = val["rel"].serialize(parentIndexed=indexed)
				else:
					usingData = None
				r = {"rel": usingData, "dest": refData}
				res.append(r)
		else:
			if skel.accessedValues[name]["dest"]:
				refData = skel.accessedValues[name]["dest"].serialize(parentIndexed=indexed)
				newRelationalLocks.add(skel.accessedValues[name]["dest"]["key"])
			else:
				refData = None
			if skel.accessedValues[name]["rel"]:
				usingData = skel.accessedValues[name]["rel"].serialize(parentIndexed=indexed)
			else:
				usingData = None
			res = {"rel": usingData, "dest": refData}
		skel.dbEntity[name] = res
		# Ensure our indexed flag is up2date
		if indexed and name in skel.dbEntity.exclude_from_indexes:
			skel.dbEntity.exclude_from_indexes.discard(name)
		elif not indexed and name not in skel.dbEntity.exclude_from_indexes:
			skel.dbEntity.exclude_from_indexes.add(name)
		# Ensure outgoing Locks are up2date
		if self.consistency != RelationalConsistency.PreventDeletion:
			# We don't need to lock anything, but may delete old locks held
			newRelationalLocks = set()
		# We should always run inside a transaction so we can safely get+put
		skel.dbEntity["%s_outgoingRelationalLocks" % name] = list(newRelationalLocks)
		for newLock in newRelationalLocks - oldRelationalLocks:
			# Lock new Entry
			referencedObj = db.Get(newLock)
			assert referencedObj, "Programming error detected?"
			if not referencedObj.get("viur_incomming_relational_locks"):
				referencedObj["viur_incomming_relational_locks"] = []
			assert skel["key"] not in referencedObj["viur_incomming_relational_locks"]
			referencedObj["viur_incomming_relational_locks"].append(skel["key"])
			db.Put(referencedObj)
		for oldLock in oldRelationalLocks - newRelationalLocks:
			# Remove Lock
			referencedObj = db.Get(oldLock)
			assert referencedObj, "Programming error detected?"
			assert isinstance(referencedObj.get("viur_incomming_relational_locks"), list), "Programming error detected?"
			assert skel["key"] in referencedObj["viur_incomming_relational_locks"], "Programming error detected?"
			referencedObj["viur_incomming_relational_locks"].remove(skel["key"])
			db.Put(referencedObj)
		return True

	def delete(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str):
		"""
			Ensure any outgoing relational lock is cleared
		:param skel:
		:param name:
		:return:
		"""
		if skel.dbEntity.get("%s_outgoingRelationalLocks" % name):
			for refKey in skel.dbEntity["%s_outgoingRelationalLocks" % name]:
				referencedEntry = db.Get(refKey)
				if not referencedEntry:
					logging.warning("Programming error detected: Entry %s is gone despite lock" % refKey)
					continue
				incommingLocks = referencedEntry.get("viur_incomming_relational_locks", [])
				# We remove any reference to ourself as multiple bones may hold Locks to the same entry
				referencedEntry["viur_incomming_relational_locks"] = [x for x in incommingLocks if x != skel["key"]]
				db.Put(referencedEntry)


	def postSavedHandler(self, skel, boneName, key):
		if not skel[boneName]:
			values = []
		elif self.multiple and self.languages:
			values = chain(*skel[boneName].values())
		elif self.languages:
			values = list(skel[boneName].values())
		elif self.multiple:
			values = skel[boneName]
		else:
			values = [skel[boneName]]
		values = [x for x in values if x is not None]
		#elif isinstance(skel[boneName], dict):
		#	values = [dict((k, v) for k, v in skel[boneName].items())]
		#else:
		#	values = [dict((k, v) for k, v in x.items()) for x in skel[boneName]]
		parentValues = db.Entity()
		srcEntity = skel.dbEntity
		parentValues.key = srcEntity.key
		for boneKey in (self.parentKeys or []):
			parentValues[boneKey] = srcEntity.get(boneKey)
		dbVals = db.Query("viur-relations")
		dbVals.filter("viur_src_kind =", skel.kindName)
		dbVals.filter("viur_dest_kind =", self.kind)
		dbVals.filter("viur_src_property =", boneName)
		dbVals.filter("src.__key__ =", key)
		for dbObj in dbVals.iter():
			try:
				if not dbObj["dest"].key in [x["dest"]["key"] for x in values]:  # Relation has been removed
					db.Delete(dbObj.key)
					continue
			except:  # This entry is corrupt
				db.Delete(dbObj.key)
			else:  # Relation: Updated
				data = [x for x in values if x["dest"]["key"] == dbObj["dest"].key][0]
				# Write our (updated) values in
				refSkel = data["dest"]
				dbObj["dest"] = refSkel.serialize(parentIndexed=True)
				dbObj["src"] = parentValues
				if self.using is not None:
					usingSkel = data["rel"]
					dbObj["rel"] = usingSkel.serialize(parentIndexed=True)
				dbObj["viur_delayed_update_tag"] = time()
				dbObj["viur_relational_updateLevel"] = self.updateLevel
				dbObj["viur_relational_consistency"] = self.consistency.value
				dbObj["viur_foreign_keys"] = self.refKeys
				db.Put(dbObj)
				values.remove(data)
		# Add any new Relation
		for val in values:
			dbObj = db.Entity(db.Key("viur-relations", parent=key))
			refSkel = val["dest"]
			dbObj["dest"] = refSkel.serialize(parentIndexed=True)
			dbObj["src"] = parentValues
			if self.using is not None:
				usingSkel = val["rel"]
				dbObj["rel"] = usingSkel.serialize(parentIndexed=True)
			dbObj["viur_delayed_update_tag"] = time()
			dbObj["viur_src_kind"] = skel.kindName  # The kind of the entry referencing
			dbObj["viur_src_property"] = boneName  # The key of the bone referencing
			dbObj["viur_dest_kind"] = self.kind
			dbObj["viur_relational_updateLevel"] = self.updateLevel
			dbObj["viur_relational_consistency"] = self.consistency.value
			dbObj["viur_foreign_keys"] = self.refKeys
			db.Put(dbObj)

	def postDeletedHandler(self, skel, boneName, key):
		dbVals = db.Query("viur-relations")  # skel.kindName+"_"+self.kind+"_"+key
		dbVals.filter("viur_src_kind =", skel.kindName)
		dbVals.filter("viur_dest_kind =", self.kind)
		dbVals.filter("viur_src_property =", boneName)
		dbVals.filter("src.key =", key)
		db.Delete([x for x in dbVals.run(keysOnly=True)])

	def isInvalid(self, key):
		return None

	def parseSubfieldsFromClient(self):
		return self.multiple and (self.using is not None)

	def singleValueFromClient(self, value, skel, name, origData):
		oldValues = skel[name]
		def restoreSkels(key, usingData, index=None):
			refSkel, usingSkel = self._getSkels()
			isEntryFromBackup = False  # If the referenced entry has been deleted, restore information from backup
			entry = None
			dbKey = None
			errors = []
			try:
				dbKey = db.keyHelper(key, self.kind)
				entry = db.Get(dbKey)
				assert entry
			except:  # Invalid key or something like that
				logging.info("Invalid reference key >%s< detected on bone '%s'",
							 key, name)
				if isinstance(oldValues, dict):
					if oldValues["dest"].key == dbKey:
						entry = oldValues["dest"]
						isEntryFromBackup = True
				elif isinstance(oldValues, list):
					for dbVal in oldValues:
						if dbVal["dest"].key == dbKey:
							entry = dbVal["dest"]
							isEntryFromBackup = True
			if isEntryFromBackup:
				refSkel = entry
			elif entry:
				refSkel.dbEntity = entry
			else:
				if index:
					errors.append(
						ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "%s.%s" % (name, index),
											"Invalid value submitted"))
				else:
					errors.append(
						ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid value submitted"))
				return None, None, errors  # We could not parse this
			if usingSkel:
				if not usingSkel.fromClient(usingData):
					errors.extend(usingSkel.errors)
			return refSkel, usingSkel, errors
		if self.using and isinstance(value, dict):
			usingData = value
			destKey = usingData["key"]
			del usingData["key"]
		else:
			destKey = value
			usingData = None
		assert isinstance(destKey, str)
		refSkel, usingSkel, errors = restoreSkels(destKey, usingData)
		if refSkel:
			return {"dest": refSkel, "rel": usingSkel}, errors
		else:
			return None, errors

	def _rewriteQuery(self, name, skel, dbFilter, rawFilter):
		"""
			Rewrites a datastore query to operate on "viur-relations" instead of the original kind.
			This is needed to perform relational queries on n:m relations.
		"""
		origFilter = dbFilter.filters
		origSortOrders = dbFilter.orders
		if isinstance(origFilter, list):
			raise NotImplementedError(
				"Doing a relational Query with multiple=True and \"IN or !=\"-filters is currently unsupported!")
		dbFilter.filters = {}
		dbFilter.kind = "viur-relations"
		dbFilter.filter("viur_src_kind =", skel.kindName)
		dbFilter.filter("viur_dest_kind =", self.kind)
		dbFilter.filter("viur_src_property", name)
		# FIXME vvvv
		# if dbFilter._origCursor:  # Merge the cursor in again (if any)
		#	dbFilter.cursor(dbFilter._origCursor)
		if origFilter:
			for k, v in origFilter.items():  # Merge old filters in
				# Ensure that all non-relational-filters are in parentKeys
				if k == db.KEY_SPECIAL_PROPERTY:
					# We must process the key-property separately as its meaning changes as we change the datastore kind were querying
					if isinstance(v, list) or isinstance(v, tuple):
						logging.warning(
							"Invalid filtering! Doing an relational Query on %s with multiple key= filters is unsupported!" % (
								name))
						raise RuntimeError()
					if not isinstance(v, db.Key):
						v = db.Key(v)
					dbFilter.ancestor(v)
					continue
				boneName = k.split(".")[0].split(" ")[0]
				if boneName not in self.parentKeys and boneName != "__key__":
					logging.warning(
						"Invalid filtering! %s is not in parentKeys of RelationalBone %s!" % (boneName, name))
					raise RuntimeError()
				dbFilter.filter("src.%s" % k, v)
		orderList = []
		for k, d in origSortOrders:  # Merge old sort orders in
			if k == db.KEY_SPECIAL_PROPERTY:
				orderList.append(("%s" % k, d))
			elif not k in self.parentKeys:
				logging.warning("Invalid filtering! %s is not in parentKeys of RelationalBone %s!" % (k, name))
				raise RuntimeError()
			else:
				orderList.append(("src.%s" % k, d))
		if orderList:
			dbFilter.order(*orderList)
		return name, skel, dbFilter, rawFilter

	def buildDBFilter(self, name, skel, dbFilter, rawFilter, prefix=None):
		#from viur.core.skeleton import RefSkel, skeletonByKind
		relSkel, _usingSkelCache = self._getSkels()
		origFilter = dbFilter.filters

		if origFilter is None:  # This query is unsatisfiable
			return (dbFilter)

		myKeys = [x for x in rawFilter.keys() if x.startswith("%s." % name)]
		if len(myKeys) > 0:  # We filter by some properties
			if dbFilter.getKind() != "viur-relations" and self.multiple:
				name, skel, dbFilter, rawFilter = self._rewriteQuery(name, skel, dbFilter, rawFilter)

			#relSkel = RefSkel.fromSkel(skeletonByKind(self.kind), *self.refKeys)

			# Merge the relational filters in
			for myKey in myKeys:
				value = rawFilter[myKey]

				try:
					unused, _type, key = myKey.split(".", 2)
					assert _type in ["dest", "rel"]
				except:
					if self.using is None:
						# This will be a "dest" query
						_type = "dest"
						try:
							unused, key = myKey.split(".", 1)
						except:
							continue
					else:
						continue

				# just use the first part of "key" to check against our refSkel / relSkel (strip any leading .something and $something)
				checkKey = key
				if "." in checkKey:
					checkKey = checkKey.split(".")[0]

				if "$" in checkKey:
					checkKey = checkKey.split("$")[0]

				if _type == "dest":

					# Ensure that the relational-filter is in refKeys
					if checkKey not in self.refKeys:
						logging.warning("Invalid filtering! %s is not in refKeys of RelationalBone %s!" % (key, name))
						raise RuntimeError()

					# Iterate our relSkel and let these bones write their filters in
					for bname, bone in relSkel.items():
						if checkKey == bname:
							newFilter = {key: value}
							if self.multiple:
								bone.buildDBFilter(bname, relSkel, dbFilter, newFilter, prefix=(prefix or "") + "dest.")
							else:
								bone.buildDBFilter(bname, relSkel, dbFilter, newFilter,
												   prefix=(prefix or "") + name + ".dest.")

				elif _type == "rel":

					# Ensure that the relational-filter is in refKeys
					if self.using is None or checkKey not in self.using():
						logging.warning("Invalid filtering! %s is not a bone in 'using' of %s" % (key, name))
						raise RuntimeError()

					# Iterate our usingSkel and let these bones write their filters in
					for bname, bone in self.using().items():
						if key.startswith(bname):
							newFilter = {key: value}
							if self.multiple:
								bone.buildDBFilter(bname, relSkel, dbFilter, newFilter, prefix=(prefix or "") + "rel.")
							else:
								bone.buildDBFilter(bname, relSkel, dbFilter, newFilter,
												   prefix=(prefix or "") + name + ".rel.")

			if self.multiple:
				dbFilter.setFilterHook(lambda s, filter, value: self.filterHook(name, s, filter, value))
				dbFilter.setOrderHook(lambda s, orderings: self.orderHook(name, s, orderings))

		elif name in rawFilter and rawFilter[name].lower() == "none":
			dbFilter = dbFilter.filter("%s =" % name, None)

		return dbFilter

	def buildDBSort(self, name, skel, dbFilter, rawFilter):
		origFilter = dbFilter.filters
		if origFilter is None or not "orderby" in rawFilter:  # This query is unsatisfiable or not sorted
			return (dbFilter)
		if "orderby" in rawFilter and isinstance(rawFilter["orderby"], str) and rawFilter["orderby"].startswith(
			"%s." % name):
			if not dbFilter.getKind() == "viur-relations":  # This query has not been rewritten (yet)
				name, skel, dbFilter, rawFilter = self._rewriteQuery(name, skel, dbFilter, rawFilter)
			key = rawFilter["orderby"]
			try:
				unused, _type, param = key.split(".")
				assert _type in ["dest", "rel"]
			except:
				return (dbFilter)  # We cant parse that
			# Ensure that the relational-filter is in refKeys
			if _type == "dest" and not param in self.refKeys:
				logging.warning("Invalid filtering! %s is not in refKeys of RelationalBone %s!" % (param, name))
				raise RuntimeError()
			if _type == "rel" and (self.using is None or param not in self.using()):
				logging.warning("Invalid filtering! %s is not a bone in 'using' of %s" % (param, name))
				raise RuntimeError()
			if "orderdir" in rawFilter and rawFilter["orderdir"] == "1":
				order = ("%s.%s" % (_type, param), db.DESCENDING)
			else:
				order = ("%s.%s" % (_type, param), db.ASCENDING)
			dbFilter = dbFilter.order(order)
			dbFilter.setFilterHook(lambda s, filter, value: self.filterHook(name, s, filter, value))
			dbFilter.setOrderHook(lambda s, orderings: self.orderHook(name, s, orderings))
		return (dbFilter)

	def filterHook(self, name, query, param, value):  # FIXME
		"""
			Hook installed by buildDbFilter.
			This rewrites all filters added to the query after buildDbFilter has been run to match the
			layout of our viur-relations index.
			Also performs sanity checks wherever this query is possible at all.
		"""
		if param.startswith("src.") or param.startswith("dest.") or param.startswith("viur_"):
			# This filter is already valid in our relation
			return (param, value)
		if param.startswith("%s." % name):
			# We add a constrain filtering by properties of the referenced entity
			refKey = param.replace("%s." % name, "")
			if " " in refKey:  # Strip >, < or = params
				refKey = refKey[:refKey.find(" ")]
			if refKey not in self.refKeys:
				logging.warning("Invalid filtering! %s is not in refKeys of RelationalBone %s!" % (refKey, name))
				raise RuntimeError()
			if self.multiple:
				return (param.replace("%s." % name, "dest."), value)
			else:
				return (param, value)
		else:
			# We filter by a property of this entity
			if not self.multiple:
				# Not relational, not multiple - nothing to do here
				return (param, value)
			# Prepend "src."
			srcKey = param
			if " " in srcKey:
				srcKey = srcKey[: srcKey.find(" ")]  # Cut <, >, and =
			if srcKey == db.KEY_SPECIAL_PROPERTY:  # Rewrite key= filter as its meaning has changed
				if isinstance(value, list) or isinstance(value, tuple):
					logging.warning(
						"Invalid filtering! Doing an relational Query on %s with multiple key= filters is unsupported!" % (
							name))
					raise RuntimeError()
				if not isinstance(value, db.Key):
					value = db.Key(value)
				query.ancestor(value)
				return (None)
			if srcKey not in self.parentKeys:
				logging.warning("Invalid filtering! %s is not in parentKeys of RelationalBone %s!" % (srcKey, name))
				raise RuntimeError()
			return ("src.%s" % param, value)

	def orderHook(self, name, query, orderings):  # FIXME
		"""
			Hook installed by buildDbFilter.
			This rewrites all orderings added to the query after buildDbFilter has been run to match the
			layout of our viur-relations index.
			Also performs sanity checks wherever this query is possible at all.
		"""
		res = []
		if not isinstance(orderings, list) and not isinstance(orderings, tuple):
			orderings = [orderings]
		for order in orderings:
			if isinstance(order, tuple):
				orderKey = order[0]
			else:
				orderKey = order
			if orderKey.startswith("dest.") or orderKey.startswith("rel.") or orderKey.startswith("src."):
				# This is already valid for our relational index
				res.append(order)
				continue
			if orderKey.startswith("%s." % name):
				k = orderKey.replace("%s." % name, "")
				if k not in self.refKeys:
					logging.warning("Invalid ordering! %s is not in refKeys of RelationalBone %s!" % (k, name))
					raise RuntimeError()
				if not self.multiple:
					res.append(order)
				else:
					if isinstance(order, tuple):
						res.append(("dest.%s" % k, order[1]))
					else:
						res.append("dest.%s" % k)
			else:
				if not self.multiple:
					# Nothing to do here
					res.append(order)
					continue
				else:
					if orderKey not in self.parentKeys:
						logging.warning(
							"Invalid ordering! %s is not in parentKeys of RelationalBone %s!" % (orderKey, name))
						raise RuntimeError()
					if isinstance(order, tuple):
						res.append(("src.%s" % orderKey, order[1]))
					else:
						res.append("src.%s" % orderKey)
		return (res)

	def refresh(self, skel, boneName):
		"""
			Refresh all values we might have cached from other entities.
		"""
		def updateInplace(relDict):
			"""
				Fetches the entity referenced by valDict["dest.key"] and updates all dest.* keys
				accordingly
			"""
			if not (isinstance(relDict, dict) and "dest" in relDict):
				logging.error("Invalid dictionary in updateInplace: %s" % relDict)
				return
			newValues = db.Get(db.keyHelper(relDict["dest"]["key"], self.kind))
			if newValues is None:
				logging.info("The key %s does not exist" % relDict["dest"]["key"])
				return
			for boneName in self.refKeys:
				if boneName != "key" and boneName in newValues:
					relDict["dest"].dbEntity[boneName] = newValues[boneName]
		if not skel[boneName] or self.updateLevel == 2:
			return
		logging.debug("Refreshing relationalBone %s of %s" % (boneName, skel.kindName))
		if isinstance(skel[boneName], dict):
			updateInplace(skel[boneName])
		elif isinstance(skel[boneName], list):
			for k in skel[boneName]:
				updateInplace(k)

	def getSearchTags(self, values, key):
		def getValues(res, skel, valuesCache):
			for k, bone in skel.items():
				if bone.searchable:
					for tag in bone.getSearchTags(valuesCache, k):
						if tag not in res:
							res.append(tag)
			return res

		_refSkelCache, _usingSkelCache = self._getSkels()
		value = values.get(key)
		res = []
		if not value:
			return res
		if self.multiple:
			for val in value:
				if val["dest"]:
					res = getValues(res, _refSkelCache, val["dest"])
				if val["rel"]:
					res = getValues(res, _usingSkelCache, val["rel"])
		else:
			if value["dest"]:
				res = getValues(res, _refSkelCache, value["dest"])
			if value["rel"]:
				res = getValues(res, _usingSkelCache, value["rel"])
		return res

	def getSearchDocumentFields(self, valuesCache, name, prefix=""):
		"""
		Generate fields for Google Search API
		"""

		def getValues(res, skel, valuesCache, searchPrefix):
			for key, bone in skel.items():
				if bone.searchable:
					res.extend(bone.getSearchDocumentFields(valuesCache, key, prefix=searchPrefix))

		_refSkelCache, _usingSkelCache = self._getSkels()
		value = valuesCache.get(name)
		res = []

		if not value:
			return res

		if self.multiple:
			for idx, val in enumerate(value):
				searchPrefix = "%s%s_%s" % (prefix, name, str(idx))
				if val["dest"]:
					getValues(res, _refSkelCache, val["dest"], searchPrefix)
				if val["rel"]:
					getValues(res, _usingSkelCache, val["rel"], searchPrefix)
		else:
			searchPrefix = "%s%s" % (prefix, name)
			if value["dest"]:
				getValues(res, _refSkelCache, value["dest"], searchPrefix)
			if value["rel"]:
				getValues(res, _usingSkelCache, value["rel"], searchPrefix)

		return res

	def setBoneValue(self, skel, boneName, value, append, *args, **kwargs):
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
		from viur.core.skeleton import RefSkel, skeletonByKind
		def relSkelFromKey(key):
			key = db.keyHelper(key, self.kind)
			entity = db.Get(key)
			if not entity:
				logging.error("Key %s not found" % str(key))
				return None
			relSkel = self._refSkelCache()
			relSkel.unserialize(entity)
			return relSkel

		if append and not self.multiple:
			raise ValueError("Bone %s is not multiple, cannot append!" % boneName)
		if not self.multiple and not self.using:
			if not (isinstance(value, str) or isinstance(value, db.KeyClass)):
				logging.error(value)
				logging.error(type(value))
				raise ValueError("You must supply exactly one Database-Key to %s" % boneName)
			realValue = (value, None)
		elif not self.multiple and self.using:
			if not isinstance(value, tuple) or len(value) != 2 or \
				not (isinstance(value[0], str) or isinstance(value[0], db.KeyClass)) or \
				not isinstance(value[1], self.using):
				raise ValueError("You must supply a tuple of (Database-Key, relSkel) to %s" % boneName)
			realValue = value
		elif self.multiple and not self.using:
			if not (isinstance(value, str) or isinstance(value, db.KeyClass)) and not (isinstance(value, list)) \
				and all([isinstance(x, str) or isinstance(x, db.Key) for x in value]):
				raise ValueError("You must supply a Database-Key or a list hereof to %s" % boneName)
			if isinstance(value, list):
				realValue = [(x, None) for x in value]
			else:
				realValue = [(value, None)]
		else:  # which means (self.multiple and self.using)
			if not (isinstance(value, tuple) and len(value) == 2 and \
					(isinstance(value[0], str) or isinstance(value[0], db.KeyClass)) \
					and isinstance(value[1], self._skeletonInstanceClassRef)) and not (isinstance(value, list) and
																   all((isinstance(x, tuple) and len(x) == 2 and \
																		(isinstance(x[0], str) or isinstance(
																			x[0], db.Key)) and isinstance(x[1], self._skeletonInstanceClassRef) for x in value))):
				raise ValueError("You must supply (db.Key, RelSkel) or a list hereof to %s" % boneName)
			if not isinstance(value, list):
				realValue = [value]
			else:
				realValue = value
		if not self.multiple:
			relSkel = relSkelFromKey(realValue[0])
			if not relSkel:
				return False
			skel[boneName] = {"dest": relSkel, "rel": realValue[1] if realValue[1] else None}
		else:
			tmpRes = []
			for val in realValue:
				relSkel = relSkelFromKey(val[0])
				if not relSkel:
					return False
				tmpRes.append({"dest": relSkel, "rel": val[1] if val[1] else None})
			if append:
				if boneName not in skel or not isinstance(skel[boneName], list):
					skel[boneName] = []
				skel[boneName].extend(tmpRes)
			else:
				skel[boneName] = tmpRes
		return True

	def getReferencedBlobs(self, skel, name):
		"""
			Returns the list of blob keys referenced from this bone
		"""
		return set()  # FIXME!
		def blobsFromSkel(skel):
			blobList = set()
			for key, _bone in skel.items():
				blobList.update(_bone.getReferencedBlobs(skel, key))
			return blobList

		_refSkelCache, _usingSkelCache = self._getSkels()
		#from viur.core.skeleton import RefSkel, skeletonByKind
		#_refSkelCache = RefSkel.fromSkel(skeletonByKind(self.kind), *self.refKeys)
		#_usingSkelCache = self.using() if self.using else None
		res = set()
		value = skel[name]
		if isinstance(value, list):
			for myDict in value:
				if myDict["dest"]:
					res.update(blobsFromSkel(myDict["dest"]))
				if myDict["rel"]:
					res.update(blobsFromSkel(myDict["rel"]))
		elif isinstance(value, dict):
			if value["dest"]:
				res.update(blobsFromSkel(value["dest"]))
			if "rel" in value and value["rel"]:
				res.update(blobsFromSkel(value["rel"]))
		return res

	def getUniquePropertyIndexValues(self, valuesCache: dict, name: str) -> List[str]:
		"""
			By default, relationalBones distinct by referenced keys. Should be overridden if a different
			behaviour is required (eg. examine values from `prop:usingSkel`)
		"""
		value = valuesCache.get(name)
		if not value:  # We don't have a value to lock
			return []
		if isinstance(value, dict):
			return self._hashValueForUniquePropertyIndex(value["dest"]["key"])
		elif isinstance(value, list):
			return self._hashValueForUniquePropertyIndex([x["dest"]["key"] for x in value])
