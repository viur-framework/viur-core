# -*- coding: utf-8 -*-
from server.bones import treeItemBone
from server import db, skeleton, request
from server.utils import normalizeKey

from hashlib import sha256
import logging

class fileBone(treeItemBone):
	type = "file"
	refKeys = ["name", "meta_mime", "metamime", "mimetype", "dlkey", "servingurl", "size"]
	
	def __init__(self, format="$(name)",*args, **kwargs ):
		super( fileBone, self ).__init__( format=format, *args, **kwargs )

	def getReferencedBlobs(self):
		if self.value is None:
			return( [] )
		elif isinstance( self.value, dict ):
			return( [self.value["dlkey"]] )
		elif isinstance( self.value, list ):
			return( [x["key"] for x in self.value])

	def unserialize( self, name, expando ):
		res = super( fileBone, self ).unserialize( name, expando )
		if not request.current.get().isDevServer:
			# Rewrite all "old" Serving-URLs to https if we are not on the development-server
			if isinstance(self.value, dict) and "servingurl" in self.value.keys():
				if self.value["servingurl"].startswith("http://"):
					self.value["servingurl"] = self.value["servingurl"].replace("http://","https://")
			elif isinstance( self.value, list ):
				for val in self.value:
					if isinstance(val, dict) and "servingurl" in val.keys():
						if val["servingurl"].startswith("http://"):
							val["servingurl"] = val["servingurl"].replace("http://","https://")
		return( res )

	def refresh(self, boneName, skel):
		"""
			Refresh all values we might have cached from other entities.
		"""

		def updateInplace(valDict):
			if "key" in valDict.keys():
				originalKey = valDict["key"]
			# !!!ViUR re-design compatibility!!!
			elif "id" in valDict.keys() and "key" not in valDict.keys():
				originalKey = valDict["id"]
			else:
				logging.error("Broken fileBone dict")
				return

			entityKey = normalizeKey(originalKey)
			if originalKey != entityKey or "key" in valDict.keys():
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

					logging.info("Refreshing file dlkey %s (%s)" % (valDict["dlkey"], valDict["servingurl"]))

		if not self.value:
			return

		logging.info("Refreshing fileBone %s of %s" % (boneName, skel.kindName))

		if isinstance(self.value, dict):
			updateInplace(self.value)

		elif isinstance( self.value, list ):
			for k in self.value:
				updateInplace(k)
