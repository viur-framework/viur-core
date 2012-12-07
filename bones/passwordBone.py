# -*- coding: utf-8 -*-
from server.bones import stringBone
from hashlib import sha512
from server.config import conf

class passwordBone( stringBone ):
	"""
		A bone holding passwords.
		This is allways empty if read from the database.
		If its saved, its ignored if its values is still empty.
		If its value is not empty, its hashed (with salt) and only the resulting hash 
		will be written to the database
	"""
	type = "password"
	
	def serialize( self, name ):
		if self.value and self.value != "":
			return( {name: sha512( self.value.encode("UTF-8")+conf["viur.salt"] ).hexdigest()} )
		return( {} )

	def unserialize( self, name, values ):
		return( {name: ""} )
