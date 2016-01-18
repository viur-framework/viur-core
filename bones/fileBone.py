# -*- coding: utf-8 -*-
from server.bones import treeItemBone, baseBone
from server import db
from server.utils import markFileForDeletion, normalizeKey
from google.appengine.api.images import get_serving_url
from server import request
import logging
from hashlib import sha256

class fileBone( treeItemBone ):
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
			return( [x["id"] for x in self.value])

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

	def refresh(self, boneName, skel ):
		"""
			Refresh all values we might have cached from other entities.
		"""
		logging.warning("Refreshing Filebone %s of %s" % (boneName, skel.kindName))
		if not self.value:
			return
		if isinstance( self.value, dict ) and "dlkey" in self.value.keys():
			# Try fixing
			try:
				oldKeyHash = sha256(self.value["dlkey"]).hexdigest().encode("hex")
				res = db.Get( db.Key.from_path("viur-blobimportmap", oldKeyHash))
				if res and "available" in res.keys() and res["available"]:
					self.value["dlkey"] = res["newkey"]
					self.value["servingurl"] = res["servingurl"]
					logging.error("Got Blobmap-Match    ghjklmarker")
				else:
					logging.error("Missing BLOB   ghjklmarker ")
			except db.EntityNotFoundError:
				logging.error("Missing BLOB 2   ghjklmarker ")
				pass
			except:
				raise
		elif isinstance( self.value, list ):
			for data in self.value:
				if isinstance(data,dict) and "dlkey" in data.keys():
					try:
						oldKeyHash = sha256(data["dlkey"]).hexdigest().encode("hex")
						res = db.Get( db.Key.from_path("viur-blobimportmap", oldKeyHash))
						if res and "available" in res.keys() and res["available"]:
							data["dlkey"] = res["newkey"]
							data["servingurl"] = res["servingurl"]
							logging.error("Got Blobmap-Match ghjklmarker")
						else:
							logging.error("Missing BLOB ghjklmarker")
					except db.EntityNotFoundError:
						logging.error("Missing BLOB 2   ghjklmarker ")
						pass
					except:
						raise

