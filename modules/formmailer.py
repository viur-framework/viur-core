# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server import errors, utils

class MailSkel(Skeleton):
	kindName="Ignored"

class Formmailer(object): #fixme
	adminInfo = None

        def __init__(self, *args, **kwargs):
            super( Formmailer, self ).__init__()

	def index( self, *args, **kwargs ):
		if not self.canUse():
			raise errors.HTTPError(401) #Unauthorized
		skel = self.mailSkel()
		if len( kwargs ) == 0:
			return self.render.add( skel=skel, failed=False)
		if not skel.fromClient( kwargs ):
			return self.render.add(  skel=skel, failed=True )
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
