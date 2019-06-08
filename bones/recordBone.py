# -*- coding: utf-8 -*-
from server.bones.bone import baseBone, getSystemInitialized
from server.errors import ReadFromClientError
import extjson


class recordBone(baseBone):
	type = "record"

	def __init__(self, using, format=None, indexed=False, multiple=True, *args, **kwargs):
		super(recordBone, self).__init__(indexed=indexed, multiple=multiple, *args, **kwargs)

		self.using = using
		self.format = format
		if not format or indexed or not multiple:
			NotImplemented("A recordBone must not be indexed, must be multiple and must have a format set")

		if getSystemInitialized():
			self._usingSkelCache = using()
		else:
			self._usingSkelCache = None

	def setSystemInitialized(self):
		super(recordBone, self).setSystemInitialized()
		self._usingSkelCache = self.using()

	def _restoreValueFromDatastore(self, val):
		"""
			Restores one of our values from the serialized data read from the datastore

			:param value: Json-Encoded datastore property

			:return: Our Value (with restored usingSkel data)
		"""
		value = extjson.loads(val)
		assert isinstance(value, dict), "Read something from the datastore thats not a dict: %s" % str(type(value))

		usingSkel = self._usingSkelCache
		usingSkel.setValuesCache({})
		usingSkel.unserialize(value)

		return usingSkel.getValuesCache()

	def unserialize(self, valuesCache, name, expando):
		if name not in expando:
			valuesCache[name] = None
			return True

		val = expando[name]

		if self.multiple:
			valuesCache[name] = []

		if not val:
			return True

		if isinstance(val, list):
			for res in val:
				try:
					valuesCache[name].append(self._restoreValueFromDatastore(res))
				except:
					raise
		else:
			try:
				valuesCache[name].append(self._restoreValueFromDatastore(val))
			except:
				raise

		return True

	def serialize(self, valuesCache, name, entity):
		if not valuesCache[name]:
			entity.set(name, None, False)

		else:
			usingSkel = self._usingSkelCache
			res = []

			for val in valuesCache[name]:
				usingSkel.setValuesCache(val)
				res.append(extjson.dumps(usingSkel.serialize()))

			entity.set(name, res, False)

		return entity

	def fromClient(self, valuesCache, name, data):
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

		errorDict = {}
		forceFail = False

		for i, r in enumerate(tmpList[:]):
			usingSkel = self._usingSkelCache
			usingSkel.setValuesCache({})

			if not usingSkel.fromClient(r):
				for k, v in usingSkel.errors.items():
					errorDict["%s.%d.%s" % (name, i, k)] = v
					forceFail = True

			tmpList[i] = usingSkel.getValuesCache()

		cleanList = []

		for item in tmpList:
			err = self.isInvalid(item)
			if err:
				errorDict["%s.%s" % (name, tmpList.index(item))] = err
			else:
				cleanList.append(item)

		valuesCache[name] = tmpList

		if not cleanList:
			if not (self.required or errorDict):
				# Returning a error will only cause a warning if we are not required
				return "No value selected!"
			errorDict[name] = "No value selected"

		if len(errorDict.keys()):
			return ReadFromClientError(errorDict, forceFail)

		return None

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

		for val in value:
			res = getValues(res, self._usingSkelCache, val)

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

		for idx, val in enumerate(value):
			getValues(res, self._usingSkelCache, val, "%s%s_%s" % (prefix, name, str(idx)))

		return res

	def getReferencedBlobs(self, valuesCache, name):
		def blobsFromSkel(skel, valuesCache):
			blobList = set()
			for key, _bone in skel.items():
				blobList.update(_bone.getReferencedBlobs(valuesCache, key))
			return blobList

		res = set()
		value = valuesCache.get(name)

		if not value:
			return res

		if isinstance(value, list):
			for val in value:
				res.update(blobsFromSkel(self._usingSkelCache, val))

		elif isinstance(value, dict):
			res.update(blobsFromSkel(self._usingSkelCache, value))

		return res
