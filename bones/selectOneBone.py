# -*- coding: utf-8 -*-
from server.bones import baseBone

class selectOneBone( baseBone ):
	type = "selectone"
	
	def __init__( self,  values = {},defaultValue=None, *args, **kwargs ):
		super( selectOneBone, self ).__init__( defaultValue=defaultValue,  *args,  **kwargs )
		self.values = values
	
	def fromClient( self, value ):
		for key in self.values.keys():
			if str(key)==str(value):
				self.value = key
				return( None )
		return( "No or invalid value selected" )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):
		mode="str"
		if all( [ isinstance( val, int ) for val in self.values.keys() ] ):
			filter = dict( [ ( k, int( v ) ) for k,v in rawFilter.items() if k==name or k.startswith("%s$" % name ) ] )
		elif all( [ isinstance( val, float ) for val in self.values.keys() ] ):
			filter = dict( [ ( k, float( v ) ) for k,v in rawFilter.items() if k==name or k.startswith("%s$" % name ) ] )
		else:
			filter=rawFilter
		return( super( selectOneBone, self ).buildDBFilter( name, skel, dbFilter, filter ) )
