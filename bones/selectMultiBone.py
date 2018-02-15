# -*- coding: utf-8 -*-
from server.bones import baseBone
from collections import OrderedDict
import logging

class selectMultiBone( baseBone ):
	type = "selectmulti"

	@staticmethod
	def generageSearchWidget(target,name="SELECTMULTI BONE",values=[]):
		return ( {"name":name,"target":target,"type":"selectmulti","values":values} )


	def __init__(self, defaultValue=[], values={}, *args, **kwargs):
		"""
			Creates a new SelectMultiBone

			:param defaultValue: List of keys which will be checked by default
			:type defaultValue: List
			:param values: Dict of key->value pairs from which the user can choose from. Values will be translated
			:type values: Dict
			:param sortBy: Either "keys" or "values". Sorts the values on clientside either by keys or by (
				translated) values
			:type sortBy: String
		"""
		super(selectMultiBone, self ).__init__(defaultValue=defaultValue, *args, **kwargs)

		if "_kindName" in kwargs:
			kindName = kwargs["_kindName"]
		else:
			kindName = "unknownKind"

		if "sortBy" in kwargs:
			logging.warning("The sortBy parameter is deprecated. Please use an orderedDict for 'values' instead")

		if isinstance(values, dict) and not isinstance(values, OrderedDict):
			vals = list(values.items())
			if "sortBy" in kwargs:
				sortBy = kwargs["sortBy"]

				if not sortBy in ["keys","values"]:
					raise ValueError( "sortBy must be \"keys\" or \"values\"" )

				if sortBy == "keys":
					vals.sort(key=lambda x: x[0])
				else:
					vals.sort(key=lambda x: x[1])
			else:
				vals.sort(key=lambda x: x[1])

			self.values = OrderedDict(vals)

		elif isinstance(values, set):
			vals = [(x, _("models.%s.%s" % (kindName, x))) for x in values]
			vals.sort(key=lambda x: x[1])
			self.values = OrderedDict(vals)

		elif isinstance(values, list):
			self.values = OrderedDict([(x, x) for x in values])

		elif isinstance(values, OrderedDict):
			self.values = values

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
		if name in data:
			values = data[name]
		else:
			values = None
		if not values:
			if not self.required:
				valuesCache[name] = []
			return "No item selected"
		if not isinstance(values, list):
			if isinstance(values, basestring):
				values = values.split(":")
			else:
				values = []
		lastErr = None
		valuesCache[name] = []
		for key, value in self.values.items():
			if str(key) in [str(x) for x in values]:
				err = self.isInvalid(key)
				if not err:
					valuesCache[name].append(key)
				else:
					lastErr = err
		if len(valuesCache[name])>0:
			return lastErr
		else:
			return "No item selected"

	def serialize( self, valuesCache, name, entity ):
		if not name in valuesCache:
			return entity
		if not valuesCache[name] or len(valuesCache[name]) == 0:
			entity.set( name, None, self.indexed )
		else:
			entity.set( name, valuesCache[name], self.indexed )
		return( entity )

	def unserialize( self, valuesCache, name, expando ):
		if name in expando:
			valuesCache[name] = expando[ name ]
			if not valuesCache[name]:
				valuesCache[name] = []
		else:
			valuesCache[name] = []
		return( True )

class selectAccessMultiBone( selectMultiBone ):
	type = "selectmulti.access"

	def __init__( self, *args, **kwargs ):
		"""
			Creates a new AccessSelectMultiBone.
			This bone encapulates elements that have a postfix "-add", "-delete",
			"-view" and "-edit" and visualizes them as a compbound unit.

			This bone is normally used in the userSkel only to provide a
			user data access right selector.
		"""
		super( selectAccessMultiBone, self ).__init__( *args, **kwargs )

