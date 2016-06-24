# -*- coding: utf-8 -*-
from server.skeleton import RelSkel
from server import errors, utils, securitykey
from server.bones import baseBone

class MailSkel(RelSkel):
	changedate = None #Changedates won't apply here

class Formmailer(object): #fixme
	adminInfo = None

	def __init__( self, moduleName, modulePath, *args, **kwargs ):
		super( Formmailer, self ).__init__()
		self.modulName = moduleName
		self.modulPath = modulePath
		

	def index( self, *args, **kwargs ):
		if not self.canUse():
			raise errors.Forbidden() #Unauthorized
		skel = self.mailSkel()
		if len( kwargs ) == 0:
			return self.render.add( skel=skel, failed=False)
		if not skel.fromClient( kwargs ) or not "skey" in kwargs.keys():
			return self.render.add(  skel=skel, failed=True )
		if not securitykey.validate( kwargs["skey"] ):
			raise errors.PreconditionFailed()
		# Allow bones to perform outstanding "magic" operations before sending the mail
		for key, _bone in skel.items():
			if( isinstance( _bone, baseBone ) ):
				_bone.performMagic( isAdd=True )
		rcpts = self.getRcpts( skel )
		utils.sendEMail( rcpts, self.mailTemplate , skel )
		self.onItemAdded( skel )
		return self.render.addItemSuccess( skel )
	index.exposed = True

	def canUse(self):
		return False

	def mailSkel(self):
		raise NotImplementedError("You must implement the \"mailSkel\" function!")
	
	def add( self,  *args,  **kwargs ):
		return self.index( *args,  **kwargs )
	add.exposed = True
	
	def onItemAdded( self, skel ):
		pass

Formmailer.jinja2=True
