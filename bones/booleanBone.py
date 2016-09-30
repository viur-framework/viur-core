# -*- coding: utf-8 -*-
from server.bones import baseBone
import logging

class booleanBone( baseBone ):
	type = "bool"
	trueStrs = [ str(True), "1", "yes" ]

	@staticmethod
	def generageSearchWidget(target,name="BOOLEAN BONE"):
		return ( {"name":name,"target":target,"type":"boolean"} )

	def __init__( self, defaultValue=False, *args, **kwargs ):
		assert defaultValue in [True, False]
		defaultValue = defaultValue
		super( booleanBone, self ).__init__( defaultValue=defaultValue,  *args,  **kwargs )

	def fromClient( self, valuesCache, name, data ):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.
			
			:param name: Our name in the skeleton
			:type name: str
			:param data: *User-supplied* request-data
			:type data: dict
			:returns: str or None
		"""
		if name in data.keys():
			value = data[ name ]
		else:
			return("No value entered!")
		if str( value ) in self.trueStrs:
			valuesCache[name] = True
		else:
			valuesCache[name] = False
		return( None )
	
	def serialize( self, valuesCache, name, entity ):
		"""
			Serializes this bone into something we
			can write into the datastore.
			
			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:returns: dict
		"""
		if name != "key":
			entity.set( name, valuesCache.get(name, False), self.indexed )
		return( entity )

	def unserialize(self, valuesCache, name, expando):
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.

			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:param expando: An instance of the dictionary-like db.Entity class
			:type expando: :class:`db.Entity`
			:returns: bool
		"""
		if name in expando.keys():
			val = expando[ name ]
			if str( val ) in self.trueStrs:
				valuesCache[name] = True
			else:
				valuesCache[name] = False
		return True

	def buildDBFilter( self, name, skel, dbFilter, rawFilter, prefix=None ):
		if name in rawFilter.keys():
			val = rawFilter[ name ]
			if str(val) in self.trueStrs:
				val = True
			else:
				val = False
			return( super( booleanBone, self ).buildDBFilter( name, skel, dbFilter, {name:val}, prefix=prefix ) )
		else:
			return( dbFilter )
