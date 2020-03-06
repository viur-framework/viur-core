# -*- coding: utf-8 -*-
from viur.core.bones import treeItemBone
from viur.core import db, request, conf
from viur.core.utils import downloadUrlFor
from viur.core.tasks import callDeferred
# from google.appengine.api import images
from hashlib import sha256
import logging
from typing import Union, Dict


@callDeferred
def ensureDerived(key: str, name: str, deriveMap: Dict[str, Dict]):
	"""
	Ensure that pending thumbnails or other derived Files are build
	:param dlkey:
	:param name:
	:param deriveMap:
	:return:
	"""
	from viur.core.skeleton import skeletonByKind
	skel = skeletonByKind("file")()
	assert skel.fromDB(key)
	if not skel["derived"]:
		logging.info("No Derives for this file")
		skel["derived"] = {}
	didBuild = False
	for fileName, params in deriveMap.items():
		if fileName not in skel["derived"]:
			deriveFuncMap = conf["viur.file.derivers"]
			if not "callee" in params:
				assert False
			if not params["callee"] in deriveFuncMap:
				raise NotImplementedError("Callee not registered")
			callee = deriveFuncMap[params["callee"]]
			callRes = callee(skel, fileName, params)
			if callRes:
				fileName, size, mimetype = callRes
				skel["derived"][fileName] = {"name": fileName, "size": size, "mimetype": mimetype, "params": params}
			didBuild = True
	if didBuild:
		skel.toDB()


class fileBone(treeItemBone):
	kind = "file"
	type = "relational.treeitem.file"
	refKeys = ["name", "key", "mimetype", "dlkey", "size", "width", "height", "derived"]

	def __init__(self, format="$(dest.name)", derive: Union[None, Dict[str, Dict]] = None, *args, **kwargs):
		assert "dlkey" in self.refKeys, "You cannot remove dlkey from refKeys!"
		super(fileBone, self).__init__(format=format, *args, **kwargs)
		self.derive = derive

	def postSavedHandler(self, skel, boneName, key):
		super().postSavedHandler(skel, boneName, key)
		# if boneName not in valuesCache:
		#	return
		# if not valuesCache.get(boneName):
		#	values = []
		# elif isinstance(valuesCache.get(boneName), dict):
		#	values = [dict((k, v) for k, v in valuesCache.get(boneName).items())]
		# else:
		#	values = [dict((k, v) for k, v in x.items()) for x in valuesCache.get(boneName)]
		values = skel[boneName]
		if self.derive and values:
			if isinstance(values, dict):
				values = [values]
			for val in values:
				ensureDerived(val["dest"].entity["key"].id_or_name, val["dest"].entity["name"], self.derive)

	def getReferencedBlobs(self, skel, name):
		val = skel[name]
		if val is None:
			return []
		elif isinstance(val, dict):
			return [val["dest"]["dlkey"]]
		elif isinstance(val, list):
			return [x["dest"]["dlkey"] for x in val]
		else:
			logging.critical("Unknown value for bone %s (%s)" % (name, str(type(val))))
			return []
			raise ValueError("Unknown value for bone %s (%s)" % (name, str(type(val))))

	def refresh(self, skel, boneName):
		"""
			Refresh all values we might have cached from other entities.
		"""
		return
		"""
		def updateInplace(relDict):
			if isinstance(relDict, dict) and "dest" in relDict:
				valDict = relDict["dest"]
			else:
				logging.error("Invalid dictionary in updateInplace: %s" % relDict)
				return

			if "key" in valDict:
				originalKey = valDict["key"]
			else:
				logging.error("Broken fileBone dict")
				return

			entityKey = originalKey
			if originalKey != entityKey:
				logging.info("Rewriting %s to %s" % (originalKey, entityKey))
				valDict["key"] = originalKey

			# Anyway, try to copy a dlkey and servingurl
			# from the corresponding viur-blobimportmap entity.
			if "dlkey" in valDict:
				try:
					oldKeyHash = sha256(valDict["dlkey"]).hexdigest().encode("hex")

					logging.info("Trying to fetch entry from blobimportmap with hash %s" % oldKeyHash)
					res = db.Get(db.Key.from_path("viur-blobimportmap", oldKeyHash))
				except:
					res = None

				if res and res["oldkey"] == valDict["dlkey"]:
					valDict["dlkey"] = res["newkey"]
					valDict["servingurl"] = res["servingurl"]

					logging.info("Refreshing file dlkey %s (%s)" % (valDict["dlkey"],
																	valDict["servingurl"]))
				else:
					if valDict["servingurl"]:
						try:
							valDict["servingurl"] = images.get_serving_url(valDict["dlkey"])
						except Exception as e:
							logging.exception(e)

		if not valuesCache[boneName]:
			return

		logging.info("Refreshing fileBone %s of %s" % (boneName, skel.kindName))
		super(fileBone, self).refresh(valuesCache, boneName, skel)

		if isinstance(valuesCache[boneName], dict):
			updateInplace(valuesCache[boneName])

		elif isinstance(valuesCache[boneName], list):
			for k in valuesCache[boneName]:
				updateInplace(k)
		"""
