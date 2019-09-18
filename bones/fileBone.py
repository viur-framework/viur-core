# -*- coding: utf-8 -*-
from server.bones import treeItemBone
from server import db, request, conf
from server.tasks import callDeferred
# from google.appengine.api import images
from hashlib import sha256
import logging
from typing import Union, Dict


@callDeferred
def ensureDerived(dlkey: str, name: str, deriveMap: Dict[str,Dict]):
	"""
	Ensure that pending thumbnails or other derived Files are build
	:param dlkey:
	:param name:
	:param deriveMap:
	:return:
	"""
	from server.skeleton import skeletonByKind
	skel = skeletonByKind("file")()
	assert skel.fromDB(dlkey)
	if not skel["derived"]:
		logging.info("No Derives for this file")
		skel["derived"] = {}
	didBuild = False
	for fileName, params in deriveMap.items():
		if not fileName in skel["derived"]:
			deriveFuncMap = conf["viur.file.derivers"]
			if not "callee" in params:
				assert False
			if not params["callee"] in deriveFuncMap:
				raise NotImplementedError("Callee not registered")
			callee = deriveFuncMap[params["callee"]]
			callRes = callee(dlkey, name, fileName, params)
			skel["derived"][fileName] = callRes
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

	def postSavedHandler(self, valuesCache, boneName, skel, key, dbfields):
		super(fileBone, self).postSavedHandler(valuesCache, boneName, skel, key, dbfields)
		if boneName not in valuesCache:
			return
		if not valuesCache.get(boneName):
			values = []
		elif isinstance(valuesCache.get(boneName), dict):
			values = [dict((k, v) for k, v in valuesCache.get(boneName).items())]
		else:
			values = [dict((k, v) for k, v in x.items()) for x in valuesCache.get(boneName)]
		if self.derive:
			for val in values:
				ensureDerived(val["dest"]["dlkey"], val["dest"]["name"], self.derive)

	def getReferencedBlobs(self, valuesCache, name):
		val = valuesCache.get(name)
		if val is None:
			return []
		elif isinstance(val, dict):
			return [val["dest"]["dlkey"]]
		elif isinstance(val, list):
			return [x["dest"]["dlkey"] for x in val]
		else:
			raise ValueError("Unknown value for bone %s (%s)" % (name, str(type(val))))

	def unserialize(self, valuesCache, name, expando):
		res = super(fileBone, self).unserialize(valuesCache, name, expando)
		currentValue = valuesCache[name]
		if not request.current.get().isDevServer:
			# Rewrite all "old" Serving-URLs to https if we are not on the development-server
			if isinstance(currentValue, dict) and currentValue["dest"].get("servingurl"):
				if currentValue["dest"]["servingurl"].startswith("http://"):
					currentValue["dest"]["servingurl"] = currentValue["dest"]["servingurl"].replace("http://",
																									"https://")
			elif isinstance(currentValue, list):
				for val in currentValue:
					if isinstance(val, dict) and val["dest"].get("servingurl"):
						if val["dest"]["servingurl"].startswith("http://"):
							val["dest"]["servingurl"] = val["dest"]["servingurl"].replace("http://", "https://")
		if isinstance(currentValue, dict):
			currentDestValue = currentValue["dest"]
			if not "mimetype" in currentDestValue or not currentDestValue["mimetype"]:
				if "meta_mime" in currentDestValue and currentDestValue["meta_mime"]:
					currentDestValue["mimetype"] = currentDestValue["meta_mime"]
				elif "metamime" in currentDestValue and currentDestValue["metamime"]:
					currentDestValue["mimetype"] = currentDestValue["metamime"]
		elif isinstance(currentValue, list):
			for val in currentValue:
				currentDestValue = val["dest"]
				if not "mimetype" in currentDestValue or not currentDestValue["mimetype"]:
					if "meta_mime" in currentDestValue and currentDestValue["meta_mime"]:
						currentDestValue["mimetype"] = currentDestValue["meta_mime"]
					elif "metamime" in currentDestValue and currentDestValue["metamime"]:
						currentDestValue["mimetype"] = currentDestValue["metamime"]
		return res

	def refresh(self, valuesCache, boneName, skel):
		"""
			Refresh all values we might have cached from other entities.
		"""
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
