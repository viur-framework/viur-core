# -*- coding: utf-8 -*-
from server.bones import treeItemBone, baseBone
from server import db
from server.utils import markFileForDeletion
from google.appengine.api.images import get_serving_url

class fileBone( treeItemBone ):
	type = "file"
	refKeys = ["name", "meta_mime", "dlkey", "servingurl", "size"]
	
	def __init__(self, format="$(name)",*args, **kwargs ):
		super( fileBone, self ).__init__( format=format, *args, **kwargs )

	def getReferencedBlobs(self):
		if self.value is None:
			return( [] )
		elif isinstance( self.value, dict ):
			return( [self.value["dlkey"]] )
		elif isinstance( self.value, list ):
			return( [x["id"] for x in self.value])

