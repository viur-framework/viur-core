# -*- coding: utf-8 -*-
from server.bones import selectOneBone

class booleanBone( selectOneBone ):
	
	def __init__( self, defaultValue=False, *args, **kwargs ):
		defaultValue = 1 if defaultValue else 0
		super( booleanBone, self ).__init__( defaultValue=defaultValue,  *args,  **kwargs )
		self.values = { 0:"No", 1:"Yes" }
	
	
	
