# -*- coding: utf-8 -*-
from viur.core.bones import baseBone
from collections import OrderedDict
import logging
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
from typing import List, Union


class selectBone(baseBone):
	type = "select"

	def __init__(self, defaultValue=None, values={}, multiple=False, *args, **kwargs):
		"""
			Creates a new selectBone.

			:param defaultValue: List of keys which will be checked by default
			:type defaultValue: list
			:param values: dict of key->value pairs from which the user can choose from. Values will be translated
			:type values: dict
		"""
		if defaultValue is None and multiple:
			defaultValue = []
		super(selectBone, self).__init__(defaultValue=defaultValue, multiple=multiple, *args, **kwargs)

		# handle sequencials as dicts
		if isinstance(values, (list, tuple)):
			values = {i: i for i in values}

		assert isinstance(values, (dict, OrderedDict)) or callable(values)
		self._values = values

	def __getattribute__(self, item):
		if item == "values":
			values = self._values
			if callable(values):
				values = values()
				assert isinstance(values, (dict, OrderedDict))

			return values

		return super().__getattribute__(item)

	def singleValueFromClient(self, value, skel, name, origData):
		if not str(value):
			return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Empty, "No value selected")]
		for key in self.values.keys():
			if str(key) == str(value):
				return key, None
		return self.getEmptyValue(), [
			ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value selected")]

	def buildDBFilter__(self, name, skel, dbFilter, rawFilter, prefix=None):
		"""
			Parses the searchfilter a client specified in his Request into
			something understood by the datastore.
			This function must:

				* Ignore all filters not targeting this bone
				* Safely handle malformed data in rawFilter
					(this parameter is directly controlled by the client)

			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:param skel: The :class:`server.db.Query` this bone is part of
			:type skel: :class:`server.skeleton.Skeleton`
			:param dbFilter: The current :class:`server.db.Query` instance the filters should be applied to
			:type dbFilter: :class:`server.db.Query`
			:param rawFilter: The dictionary of filters the client wants to have applied
			:type rawFilter: dict
			:returns: The modified :class:`server.db.Query`
		"""
		if not self.multiple:
			return super(selectBone, self).buildDBFilter(name, skel, dbFilter, rawFilter, prefix)

		if name in rawFilter:
			dbFilter.filter((prefix or "") + name + " AC", rawFilter[name])
