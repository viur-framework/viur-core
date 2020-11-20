# -*- coding: utf-8 -*-
from viur.core.bones.bone import baseBone, getSystemInitialized
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
from typing import List, Union
import copy, logging

try:
	import extjson
except ImportError:
	# FIXME: That json will not read datetime objects
	import json as extjson


class recordBone(baseBone):
	type = "record"

	def __init__(self, using, format=None, multiple=True, indexed=False, *args, **kwargs):
		super(recordBone, self).__init__(multiple=multiple, *args, **kwargs)
		self.using = using
		self.format = format
		if not format or indexed or not multiple:
			raise NotImplementedError("A recordBone must not be indexed, must be multiple and must have a format set")

	def setSystemInitialized(self):
		super(recordBone, self).setSystemInitialized()

	# self._usingSkelCache = self.using()

	def singleValueUnserialize(self, val, skel: 'viur.core.skeleton.SkeletonInstance', name: str):
		if isinstance(val, str):
			try:
				value = extjson.loads(val)
			except:
				value = None
		else:
			value = val
		if not value:
			return None
		elif isinstance(value, list) and value:
			value = value[0]
		assert isinstance(value, dict), "Read something from the datastore thats not a dict: %s" % str(type(value))
		usingSkel = self.using()
		usingSkel.unserialize(value)
		return usingSkel

	def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
		return value.serialize(parentIndexed=False)

	def parseSubfieldsFromClient(self) -> bool:
		"""
		Whenever this request should try to parse subfields submitted from the client.
		Set only to true if you expect a list of dicts to be transmitted
		"""
		return True

	def singleValueFromClient(self, value, skel, name, origData):
		usingSkel = self.using()
		usingSkel.fromClient(value)
		return usingSkel, usingSkel.errors

	def getSearchTags(self, values, key):
		def getValues(res, skel, valuesCache):
			for k, bone in skel.items():
				if bone.searchable:
					for tag in bone.getSearchTags(valuesCache, k):
						if tag not in res:
							res.append(tag)
			return res

		value = values[key]
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
