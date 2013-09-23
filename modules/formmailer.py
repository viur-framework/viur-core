# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server import errors, utils
from server.bones import baseBone

class MailSkel(Skeleton):
	kindName="Ignored"
	changedate = None #Changedates won't apply here

class Formmailer(object): #fixme
	adminInfo = None

	def __init__( self, modulName, modulPath, *args, **kwargs ):
		super( Formmailer, self ).__init__()
		self.modulName = modulName
		self.modulPath = modulPath
		

	def index( self, *args, **kwargs ):
		if not self.canUse():
			raise errors.HTTPError(401) #Unauthorized
		skel = self.mailSkel()
		if len( kwargs ) == 0:
			return self.render.add( skel=skel, failed=False)
		if not skel.fromClient( kwargs ):
			return self.render.add(  skel=skel, failed=True )
		# Allow bones to perform outstanding "magic" operations before sending the mail
		for key in dir( skel ):
			if "__" not in key:
				_bone = getattr( skel, key )
				if( isinstance( _bone, baseBone ) ):
					_bone.performMagic( isAdd=True )
		rcpts = self.getRcpts( skel )
		utils.sendEMail( rcpts, self.mailTemplate , skel )
		self.onItemAdded( rcpts, skel )
		return self.render.addItemSuccess( None, skel )
	index.exposed = True
	
	def add( self,  *args,  **kwargs ):
		return self.index( *args,  **kwargs )
	add.exposed = True
	
	def onItemAdded( self, rcpts, skel ):
		pass

Formmailer.jinja2=True
