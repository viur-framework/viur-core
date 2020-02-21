# -*- coding: utf-8 -*-
from viur.core.bones.bone import baseBone, getSystemInitialized
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
from typing import List
import copy


class recordBone(baseBone):
	type = "record"

	def __init__(self, using, format=None, multiple=True, indexed=False, *args, **kwargs):
		super(recordBone, self).__init__(multiple=multiple, *args, **kwargs)

		self.using = using
		self.format = format
		if not format or indexed or not multiple:
			raise NotImplementedError("A recordBone must not be indexed, must be multiple and must have a format set")

		#if getSystemInitialized():
		#	self._usingSkelCache = using()
		#else:
		#	self._usingSkelCache = None

	def setSystemInitialized(self):
		super(recordBone, self).setSystemInitialized()
		#self._usingSkelCache = self.using()

	def _restoreValueFromDatastore(self, val):
		"""
			Restores one of our values from the serialized data read from the datastore

			:param value: Json-Encoded datastore property

			:return: Our Value (with restored usingSkel data)
		"""
		value = val
		assert isinstance(value, dict), "Read something from the datastore thats not a dict: %s" % str(type(value))

		usingSkel = self.using()
		usingSkel.setValuesCache({})
		usingSkel.unserialize(value)
		return usingSkel.getValuesCache()

	def unserialize(self, skeletonValues, name):
		if name not in skeletonValues.entity:
			return False
		val = skeletonValues.entity[name]
		skeletonValues.accessedValues[name] = []
		if not val:
			return True
		if isinstance(val, list):
			for res in val:
				try:
					skeletonValues.accessedValues[name].append(self._restoreValueFromDatastore(res))
				except:
					raise
		else:
			try:
				skeletonValues.accessedValues[name].append(self._restoreValueFromDatastore(val))
			except:
				raise

		return True

	def serialize(self, skeletonValues, name):
		if name in skeletonValues.accessedValues:
			value = skeletonValues.accessedValues[name]
			print("xxxxx")
			print(value)
			if not value:
				skeletonValues.entity[name] = []
			else:
				usingSkel = self.using()
				res = []
				for val in value:
					usingSkel.setValuesCache(val)
					res.append(usingSkel.serialize())
				skeletonValues.entity[name] = res
			return True
		return False

	def fromClient(self, valuesCache, name, data):
		#return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Not yet fixed")]
		if not name in data and not any(x.startswith("%s." % name) for x in data):
			return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, name, "Field not submitted")]

		valuesCache[name] = []
		tmpRes = {}

		clientPrefix = "%s." % name

		for k, v in data.items():
			# print(k, v)

			if k.startswith(clientPrefix) or k == name:
				if k == name:
					k = k.replace(name, "", 1)

				else:
					k = k.replace(clientPrefix, "", 1)

				if "." in k:
					try:
						idx, bname = k.split(".", 1)
						idx = int(idx)
					except ValueError:
						idx = 0

						try:
							bname = k.split(".", 1)
						except ValueError:
							# We got some garbage as input; don't try to parse it
							continue

				else:
					idx = 0
					bname = k

				if not bname:
					continue

				if not idx in tmpRes:
					tmpRes[idx] = {}

				if bname in tmpRes[idx]:
					if isinstance(tmpRes[idx][bname], list):
						tmpRes[idx][bname].append(v)
					else:
						tmpRes[idx][bname] = [tmpRes[idx][bname], v]
				else:
					tmpRes[idx][bname] = v

		tmpList = [tmpRes[k] for k in sorted(tmpRes.keys())]

		errors = []

		for i, r in enumerate(tmpList[:]):
			usingSkel = self.using()
			#usingSkel.setValuesCache(Skeletccc)
			usingSkel.unserialize({})

			if not usingSkel.fromClient(r):
				for error in usingSkel.errors:
					errors.append(
						ReadFromClientError(error.severity, "%s.%s.%s" % (name, i, error.fieldPath), error.errorMessage)
					)
			tmpList[i] = usingSkel.getValuesCache()

		cleanList = []

		for item in tmpList:
			err = self.isInvalid(item)
			if err:
				errors.append(
					ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "%s.%s" % (name, tmpList.index(item)), err)
				)
			else:
				cleanList.append(item)

		valuesCache[name] = tmpList

		if not cleanList:
			errors.append(
				ReadFromClientError(ReadFromClientErrorSeverity.Empty, name, "No value selected")
			)

		if errors:
			return errors


	def setBoneValue(self, valuesCache, boneName, value, append):
		if not isinstance(value, self.using):
			raise ValueError("value (=%r) must be of type %r" % (type(value), self.using))

		if valuesCache[boneName] is None or not append:
			valuesCache[boneName] = []

		valuesCache[boneName].append(copy.deepcopy(value.getValuesCache()))
		return True

	def getSearchTags(self, values, key):
		def getValues(res, skel, valuesCache):
			for k, bone in skel.items():
				if bone.searchable:
					for tag in bone.getSearchTags(valuesCache, k):
						if tag not in res:
							res.append(tag)
			return res

		value = values.get(key)
		res = []

		if not value:
			return res
		uskel = self.using()
		for val in value:
			res = getValues(res, uskel, val)

		return res

	def getSearchDocumentFields(self, valuesCache, name, prefix=""):
		def getValues(res, skel, valuesCache, searchPrefix):
			for key, bone in skel.items():
				if bone.searchable:
					res.extend(bone.getSearchDocumentFields(valuesCache, key, prefix=searchPrefix))

		value = valuesCache.get(name)
		res = []

		if not value:
			return res
		uskel = self.using()
		for idx, val in enumerate(value):
			getValues(res, uskel, val, "%s%s_%s" % (prefix, name, str(idx)))

		return res

	def getReferencedBlobs(self, skel, name):
		def blobsFromSkel(relSkel, valuesCache):
			blobList = set()
			for key, _bone in relSkel.items():
				blobList.update(_bone.getReferencedBlobs(relSkel, key))
			return blobList

		res = set()
		value = skel[name]

		if not value:
			return res
		uskel = self.using()
		if isinstance(value, list):
			for val in value:
				res.update(blobsFromSkel(uskel, val))

		elif isinstance(value, dict):
			res.update(blobsFromSkel(uskel, value))

		return res

	def getUniquePropertyIndexValues(self, valuesCache: dict, name: str) -> List[str]:
		"""
			This is intentionally not defined as we don't now how to derive a key from the relskel
			being using (ie. which Fields to include and how).

		"""
		raise NotImplementedError
