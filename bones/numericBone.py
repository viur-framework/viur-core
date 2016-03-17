# -*- coding: utf-8 -*-
from server.bones import baseBone
from math import pow

class numericBone( baseBone ):
	"""
		Holds numeric values.
		Can be used for ints and floats.
		For floats, the precision can be specified in decimal-places.
	"""
	@staticmethod
	def generageSearchWidget(target,name="NUMERIC BONE",mode="range"):
		return ( {"name":name,"mode":mode,"target":target,"type":"numeric"} )

	type = "numeric"

	def __init__(self, precision=0, min=-int( pow(2, 30) ), max=int( pow(2, 30) ), *args,  **kwargs ):
		"""
			Initializes a new NumericBone.

			:param precision: How may decimal places should be saved. Zero casts the value to int instead of float.
			:type precision: int
			:param min: Minimum accepted value (including).
			:type min: float
			:param max: Maximum accepted value (including).
			:type max: float
		"""
		baseBone.__init__( self,  *args,  **kwargs )
		self.precision = precision
		if not self.precision and "mode" in kwargs.keys() and kwargs["mode"]=="float": #Fallback for old API
			self.precision = 8
		self.min = min
		self.max = max

	def fromClient( self, name, data ):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.
			
			:param name: Our name in the skeleton
			:type name: String
			:param data: *User-supplied* request-data
			:type data: Dict
			:returns: None or String
		"""
		if name in data.keys():
			value = data[ name ]
		else:
			value = None
		try:
			value = str( value ).replace(",", ".", 1)
		except:
			self.value = None
			return( "Invalid value entered" )
		if self.precision and ( str( value ).replace(".","",1).replace("-", "", 1).isdigit() ) and float( value )>=self.min and float( value )<=self.max:
				self.value = round( float( value ), self.precision )
				return( None )
		elif not self.precision and ( str( value ).replace("-", "", 1).isdigit() ) and int( value )>=self.min and int( value )<=self.max:
				self.value = int( value )
				return( None )
		else:
			self.value = None
			return( "Invalid value entered" )
	
	def serialize( self, name, entity ):
		if isinstance( self.value,  float ) and self.value!= self.value: # NaN
			entity.set( name, None, self.indexed )
		else:
			entity.set( name, self.value, self.indexed )
		return( entity )
		
	def unserialize( self, name, expando ):
		if not name in expando.keys():
			self.value = None
			return
		if expando[ name ]==None or not str(expando[ name ]).replace(".", "", 1).lstrip("-").isdigit():
			self.value = None
		else:
			if not self.precision:
				self.value = int( expando[ name ] )
			else:
				self.value = float( expando[ name ] )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter, prefix=None ):
		if not self.precision:
			filter = dict( [ ( k, int( v ) ) for k,v in rawFilter.items() if k.startswith( name ) ] )
		else:
			filter = dict( [ ( k, float( v ) ) for k,v in rawFilter.items() if k.startswith( name ) ] )
		return( super( numericBone, self ).buildDBFilter( name, skel, dbFilter, filter, prefix ) )
