# -*- coding: utf-8 -*-
import time, json
from string import Template
import default

class UserRender( default.DefaultRender ): #Render user-data to json

	def login( self, skel, **kwargs ):
		return( self.edit( skel,  **kwargs ) )

	def loginSucceeded( self,  **kwargs ):
		return( json.dumps( "OKAY" ) )

	def logoutSuccess(self, **kwargs ):
		return( json.dumps( "OKAY" ) )

	def verifySuccess( self, skel, **kwargs ):
		return( json.dumps( "OKAY" ) )
	
	def verifyFailed( self,  **kwargs ):
		return( json.dumps( "FAILED" ) )

	def passwdRecoverInfo( self, msg, skel=None, tpl=None, **kwargs ):
		if skel:
			return( self.edit( skel,  **kwargs ) )
		else:
			return( json.dumps( msg ) )
	
	def passwdRecover(self, *args, **kwargs ):
		return( self.edit( *args, **kwargs ) )

