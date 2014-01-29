# -*- coding: utf-8 -*-
from server.bones import baseBone
import logging

class booleanBone( baseBone ):
	type = "bool"
	trueStrs = [ str(True), "1", "yes" ]
	
	def __init__( self, defaultValue=False, *args, **kwargs ):
		assert defaultValue in [True, False]
		defaultValue = defaultValue
		super( booleanBone, self ).__init__( defaultValue=defaultValue,  *args,  **kwargs )

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
			return("No value entered!")
		if str( value ) in self.trueStrs:
			self.value = True
		else:
			self.value = False
		return( None )
	
	def serialize( self, name, entity ):
		"""
			Serializes this bone into something we
			can write into the datastore.
			
			@param name: The property-name this bone has in its Skeleton (not the description!)
			@type name: String
			@returns: Dict
		"""
		if name != "id":
			entity.set( name, self.value, self.indexed )
		return( entity )

	def unserialize( self, name, expando ):
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.
			@param name: The property-name this bone has in its Skeleton (not the description!)
			@type name: String
			@param expando: An instance of the dictionary-like db.Entity class
			@type expando: db.Entity
		"""
		if name in expando.keys():
			val = expando[ name ]
			if str( val ) in self.trueStrs:
				self.value = True
			else:
				self.value = False
		return( True )

	def buildDBFilter( self, name, skel, dbFilter, rawFilter ):	
		if name in rawFilter.keys():
			val = rawFilter[ name ]
			if str(val) in self.trueStrs:
				val = True
			else:
				val = False
			return( super( booleanBone, self ).buildDBFilter( name, skel, dbFilter, {name:val} ) )
		else:
			return( dbFilter )
	
