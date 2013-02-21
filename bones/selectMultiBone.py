# -*- coding: utf-8 -*-
from server.bones import baseBone

class selectMultiBone( baseBone ):
	type = "selectmulti"
	def __init__( self, defaultValue=[],  values = {}, *args, **kwargs ):
		super( selectMultiBone, self ).__init__( defaultValue=defaultValue, *args, **kwargs )
		self.values = values

	def fromClient( self, values ):
		self.value = []
		if not values:
			return( "No item selected" )
		if not isinstance( values, list ):
			if isinstance( values, basestring):
				values = values.split( ":" )
			else:
				values = []
		for name, value in self.values.items():
			if str(name) in [str(x) for x in values]:
				self.value.append( name )
		if len( self.value )>0:
			return( None )
		else:
			return( "No item selected" )
	
	def serialize( self, name ):
		if not self.value or len( self.value ) == 0:
			return( {name: None } )
		else:
			return( {name: self.value } )

	def unserialize( self, name, expando ):
		if name in expando.keys():
			self.value = expando[ name ]
		if not self.value:
			self.value = []
		return( True )

