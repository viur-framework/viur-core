# -*- coding: utf-8 -*-
from server.bones import treeItemBone
from server import db, request
from server.utils import normalizeKey

from hashlib import sha256
import logging

class fileBone(treeItemBone):
	type = "file"
	refKeys = ["name", "meta_mime", "metamime", "mimetype", "dlkey", "servingurl", "size"]
	
	def __init__(self, format="$(name)",*args, **kwargs ):
		super( fileBone, self ).__init__( format=format, *args, **kwargs )

	def getReferencedBlobs(self):
		if self.value is None or not "dlkey" in self.refKeys:
			return []
		elif isinstance(self.value, dict):
			return [self.value["dest"]["dlkey"].value]
		elif isinstance(self.value, list):
			return [x["dest"]["dlkey"].value for x in self.value]

	def unserialize( self, name, expando ):
		res = super( fileBone, self ).unserialize( name, expando )
		if not request.current.get().isDevServer:
			# Rewrite all "old" Serving-URLs to https if we are not on the development-server
			if isinstance(self.value, dict) and "servingurl" in self.value["dest"].keys():
				if self.value["dest"]["servingurl"].value.startswith("http://"):
					self.value["dest"]["servingurl"].value = self.value["dest"]["servingurl"].value.replace("http://","https://")
			elif isinstance( self.value, list ):
				for val in self.value:
					if isinstance(val, dict) and "servingurl" in val["dest"].keys():
						if val["dest"]["servingurl"].value.startswith("http://"):
							val["dest"]["servingurl"].value = val["dest"]["servingurl"].value.replace("http://","https://")
		return res

	def refresh(self, boneName, skel):
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
				originalKey = valDict["key"].value
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
					oldKeyHash = sha256(valDict["dlkey"].value).hexdigest().encode("hex")

					logging.info("Trying to fetch entry from blobimportmap with hash %s" % oldKeyHash)
					res = db.Get(db.Key.from_path("viur-blobimportmap", oldKeyHash))
				except:
					res = None

				if res and res["oldkey"] == valDict["dlkey"].value:
					valDict["dlkey"].value = res["newkey"]
					valDict["servingurl"].value = res["servingurl"]

					logging.info("Refreshing file dlkey %s (%s)" % (valDict["dlkey"].value,
					                                                valDict["servingurl"].value))

		if not self.value:
			return

		logging.info("Refreshing fileBone %s of %s" % (boneName, skel.kindName))
		super(fileBone, self).refresh(boneName, skel)

		if isinstance(self.value, dict):
			updateInplace(self.value)

		elif isinstance(self.value, list):
			for k in self.value:
				updateInplace(k)
