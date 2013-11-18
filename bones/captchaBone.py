# -*- coding: utf-8 -*-
from server.bones import bone
from server import request
import urllib
from google.appengine.api import urlfetch 
import logging

#Fixme: Read the global dict
class captchaBone( bone.baseBone ):
	type = "captcha"
	
	def __init__(self, publicKey=None, privateKey=None, *args,  **kwargs ):
		bone.baseBone.__init__(self,  *args,  **kwargs )
		self.value = publicKey
		self.privateKey = privateKey
		self.required = True
		self.hasDBField = False
	
	def serialize( self, name, entity ):
		return( entity )

	def unserialize( self, name, values ):
		return( {name: ""} )
		
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
		if request.current.get().isDevServer: #We dont enforce captchas on dev server
			return( None )
		if not "recaptcha_challenge_field" in data.keys() or not "recaptcha_response_field" in data.keys():
			return( u"No Captcha given!" )
		data = { 	"privatekey": self.privateKey,
				"remoteip": request.current.get().request.remote_addr,
				"challenge": data["recaptcha_challenge_field"],
				"response": data["recaptcha_response_field"]
			}
		response = urlfetch.fetch(	url="http://www.google.com/recaptcha/api/verify",
						payload=urllib.urlencode( data ),
						method=urlfetch.POST,
						headers={"Content-Type": "application/x-www-form-urlencoded"} )
		if str(response.content).strip().lower().startswith("true"):
			return( None )
		return( u"Invalid Captcha" )

