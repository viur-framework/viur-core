# -*- coding: utf-8 -*-
from server.bones import baseBone

class selectMultiBone( baseBone ):
	type = "selectmulti"

	@staticmethod
	def generageSearchWidget(target,name="SELECTMULTI BONE",values=[]):
		return ( {"name":name,"target":target,"type":"selectmulti","values":values} )


	def __init__( self, defaultValue=[],  values = {}, sortBy="keys", *args, **kwargs ):
		"""
			Creates a new SelectMultiBone
			@param defaultValue: List of keys which will be checked by default
			@type defaultValue: List
			@param values: Dict of key->value pairs from which the user can choose from. Values will be translated
			@type values: Dict
			@param sortBy: Either "keys" or "values". Sorts the values on clientside either by keys or by (translated) values
			@type sortBy: String
		"""
		super( selectMultiBone, self ).__init__( defaultValue=defaultValue, *args, **kwargs )
		if not sortBy in ["keys","values"]:
			raise ValueError( "sortBy must be \"keys\" or \"values\"" )
		self.sortBy = sortBy
		self.values = values

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
		if name in data.keys():
			values = data[ name ]
		else:
			values = None
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
	
	def serialize( self, name, entity ):
		if not self.value or len( self.value ) == 0:
			entity.set( name, None, self.indexed )
		else:
			entity.set( name, self.value, self.indexed )
		return( entity )

	def unserialize( self, name, expando ):
		if name in expando.keys():
			self.value = expando[ name ]
		if not self.value:
			self.value = []
		return( True )

class selectAccessMultiBone( selectMultiBone ):
	type = "accessselectmulti"

	def __init__( self, *args, **kwargs ):
		"""
			Creates a new AccessSelectMultiBone.
			This bone encapulates elements that have a postfix "-add", "-delete",
			"-view" and "-edit" and visualizes them as a compbound unit.

			This bone is normally used in the userSkel only to provide a
			user data access right selector.
		"""
		super( selectAccessMultiBone, self ).__init__( *args, **kwargs )

