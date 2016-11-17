# -*- coding: utf-8 -*-
from server.bones import treeItemBone
from server import db, request
from server.utils import normalizeKey

from hashlib import sha256
import logging

class fileBone(treeItemBone):
	kind = "file"
	refKeys = ["key", "name", "meta_mime", "metamime", "mimetype", "dlkey", "servingurl", "size"]

	def __init__(self, format="$(dest.name)",*args, **kwargs ):
		assert "dlkey" in self.refKeys, "You cannot remove dlkey from refKeys!"
		super( fileBone, self ).__init__( format=format, *args, **kwargs )

	def getReferencedBlobs(self, valuesCache, name):
		if valuesCache[name] is None:
			return []
		elif isinstance(valuesCache[name], dict):
			return [valuesCache[name]["dest"]["dlkey"]]
		elif isinstance(valuesCache[name], list):
			return [x["dest"]["dlkey"] for x in valuesCache[name]]
		else:
			raise ValueError("Unknown value for bone %s (%s)" % (name, str(type(valuesCache[name]))))

	def unserialize( self, valuesCache, name, expando ):
		res = super( fileBone, self ).unserialize( valuesCache, name, expando )
		if not request.current.get().isDevServer:
			# Rewrite all "old" Serving-URLs to https if we are not on the development-server
			if isinstance(valuesCache[name], dict) and "servingurl" in valuesCache[name]["dest"].keys():
				if valuesCache[name]["dest"]["servingurl"].startswith("http://"):
					valuesCache[name]["dest"]["servingurl"] = valuesCache[name]["dest"]["servingurl"].replace("http://","https://")
			elif isinstance( valuesCache[name], list ):
				for val in valuesCache[name]:
					if isinstance(val, dict) and "servingurl" in val["dest"].keys():
						if val["dest"]["servingurl"].startswith("http://"):
							val["dest"]["servingurl"] = val["dest"]["servingurl"].replace("http://","https://")
		return res

	def refresh(self, valuesCache, boneName, skel):
		"""
			Refresh all values we might have cached from other entities.
		"""

		def updateInplace(relDict):
			if isinstance(relDict, dict) and "dest" in relDict.keys():
				valDict = relDict["dest"]
			else:
				logging.error("Invalid dictionary in updateInplace: %s" % relDict)
				return

			if "key" in valDict.keys():
				originalKey = valDict["key"]
			else:
				logging.error("Broken fileBone dict")
				return

			entityKey = normalizeKey(originalKey)
			if originalKey != entityKey:
				logging.info("Rewriting %s to %s" % (originalKey, entityKey))
				valDict["key"] = originalKey

			# Anyway, try to copy a dlkey and servingurl
			# from the corresponding viur-blobimportmap entity.
			if "dlkey" in valDict.keys():
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

		if not valuesCache[boneName]:
			return

		logging.info("Refreshing fileBone %s of %s" % (boneName, skel.kindName))
		super(fileBone, self).refresh(valuesCache, boneName, skel)

		if isinstance(valuesCache[boneName], dict):
			updateInplace(valuesCache[boneName])

		elif isinstance(valuesCache[boneName], list):
			for k in valuesCache[boneName]:
				updateInplace(k)
