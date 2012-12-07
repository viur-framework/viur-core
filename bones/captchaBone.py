# -*- coding: utf-8 -*-
from server.bones import bone
from server import request
import urllib
from google.appengine.api import urlfetch 

#Fixme: Read the global dict
class captchaBone( bone.baseBone ):
	type = "captcha"
	
	def __init__(self, publicKey=None, privateKey=None, *args,  **kwargs ):
		bone.baseBone.__init__(self,  *args,  **kwargs )
		self.value = publicKey
		self.privateKey = privateKey
		self.required = True
		self.hasDBField = False
	
	def serialize( self, name ):
		return( {} )

	def unserialize( self, name, values ):
		return( {name: ""} )
		
	def fromClient( self, value ): #fixme
		reqData = request.current.get().kwargs
		if not "recaptcha_challenge_field" in reqData.keys() or not "recaptcha_response_field" in reqData.keys():
			return( False )
		data = { 	"privatekey": self.privateKey,
				"remoteip": request.current.get().request.remote_addr,
				"challenge": reqData["recaptcha_challenge_field"],
				"response": reqData["recaptcha_response_field"]
			}
		response = urlfetch.fetch(	url="http://www.google.com/recaptcha/api/verify",
						payload=urllib.urlencode( data ),
						method=urlfetch.POST,
						headers={"Content-Type": "application/x-www-form-urlencoded"} )
		if str(response.content).strip().lower().startswith("true"):
			return( False )
		return( u"Invalid Captcha" )

