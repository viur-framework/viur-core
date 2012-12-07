# -*- coding: utf-8 -*-
from server.bones.relationalBone import relationalBone
from server.config import conf
from google.appengine.api import users

class userBone( relationalBone ):
	type = "user"
	datafields = ["name"]
	
	def __init__( self,  creationMagic=False, updateMagic=False, *args,  **kwargs ):
		super( userBone, self ).__init__( *args, **kwargs )
		if creationMagic or updateMagic:
			self.visible = False
			self.multiple = False
		self.creationMagic = creationMagic
		self.updateMagic = updateMagic


	def fromClient( self, value ): #fixme
		if self.updateMagic or (self.creationMagic and not self.value):
			user = conf["viur.mainApp"].user.getCurrentUser()
			if user:
				return( super( userBone, self).fromClient( str(user["id"]) ) )
			else:
				return( super( userBone, self).fromClient( None ) )
		return( relationalBone.fromClient( self, value ) )
		

