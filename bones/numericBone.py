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
		if not self.precision and "mode" in kwargs and kwargs["mode"]=="float": #Fallback for old API
			self.precision = 8
		self.min = min
		self.max = max

	def fromClient( self, valuesCache, name, data ):
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
		rawValue = data.get(name, None)
		value = None
		if rawValue:
			try:
				rawValue = str(rawValue).replace(",", ".", 1)
			except:
				value = None
			else:
				if self.precision and (str(rawValue).replace(".","",1).replace("-", "", 1).isdigit()) and float(rawValue)>=self.min and float(rawValue)<=self.max:
					value = round(float(rawValue), self.precision)
				elif not self.precision and (str(rawValue).replace("-", "", 1).isdigit()) and int(rawValue)>=self.min and int(rawValue)<=self.max:
					value = int(rawValue)
				else:
					value = None
		err = self.isInvalid(value)
		if not err:
			valuesCache[name] = value
			if value is None:
				return "No value entered"
		return err


	def serialize( self, valuesCache, name, entity ):
		if isinstance( valuesCache[name],  float ) and valuesCache[name]!= valuesCache[name]: # NaN
			entity.set( name, None, self.indexed )
		else:
			entity.set( name, valuesCache[name], self.indexed )
		return( entity )

	def unserialize( self, valuesCache ,name, expando ):
		if not name in expando:
			valuesCache[name] = None
			return
		if expando[ name ]==None or not str(expando[ name ]).replace(".", "", 1).lstrip("-").isdigit():
			valuesCache[name] = None
		else:
			if not self.precision:
				valuesCache[name] = int( expando[ name ] )
			else:
				valuesCache[name] = float( expando[ name ] )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter, prefix=None ):
		if not self.precision:
			filter = dict( [ ( k, int( v ) ) for k,v in rawFilter.items() if k.startswith( name ) ] )
		else:
			filter = dict( [ ( k, float( v ) ) for k,v in rawFilter.items() if k.startswith( name ) ] )
		return( super( numericBone, self ).buildDBFilter( name, skel, dbFilter, filter, prefix ) )
