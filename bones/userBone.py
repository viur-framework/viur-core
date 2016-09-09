# -*- coding: utf-8 -*-
from server.bones.relationalBone import relationalBone
from server.config import conf


class userBone(relationalBone):
	kind = "user"
	datafields = ["name"]

	def __init__( self,  creationMagic=False, updateMagic=False, *args,  **kwargs ):
		super( userBone, self ).__init__( *args, **kwargs )

		if creationMagic or updateMagic:
			self.visible = False
			self.multiple = False

		self.creationMagic = creationMagic
		self.updateMagic = updateMagic

	def performMagic( self, isAdd, *args, **kwargs ):
		return
		if self.updateMagic or (self.creationMagic and isAdd):
			user = conf["viur.mainApp"].user.getCurrentUser()
			if user:
				return self.fromClient( "user", {"user": str(user["key"]) } )
			else:
				return self.fromClient( "user", {} )
		
