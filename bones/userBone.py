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


	def fromClient( self, name, data ):
		"""
			Reads a value from the client.
			If this value is valis for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.
			
			@param name: Our name in the skeleton
			@type name: String
			@param data: *User-supplied* request-data
			@type data: Dict
			@returns: None or String
		"""
		if name in data.keys():
			value = data[ name ]
		else:
			value = None
		if self.updateMagic or (self.creationMagic and not self.value):
			user = conf["viur.mainApp"].user.getCurrentUser()
			if user:
				return( super( userBone, self).fromClient( str(user["id"]) ) )
			else:
				return( super( userBone, self).fromClient( None ) )
		return( relationalBone.fromClient( self, value ) )
		

