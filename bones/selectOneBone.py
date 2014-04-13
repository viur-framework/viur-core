# -*- coding: utf-8 -*-
from server.bones import baseBone

class selectOneBone( baseBone ):
	type = "selectone"

	@staticmethod
	def generageSearchWidget(target,name="SELECTONE BONE",values=[]):
		return ( {"name":name,"values":values,"target":target,"type":"selectone"} )

	def __init__( self,  values = {}, defaultValue=None, sortBy="keys", *args, **kwargs ):
		"""
			Creates a new selectOneBone
			@param defaultValue: List of keys which will be checked by default
			@type defaultValue: List
			@param values: Dict of key->value pairs from which the user can choose from. Values will be translated
			@type values: Dict
			@param sortBy: Either "keys" or "values". Sorts the values on clientside either by keys or by (translated) values
			@type sortBy: String
		"""
		super( selectOneBone, self ).__init__( defaultValue=defaultValue,  *args,  **kwargs )
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
			value = data[ name ]
		else:
			value = None
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
