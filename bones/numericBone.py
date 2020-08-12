# -*- coding: utf-8 -*-
from viur.core.bones import baseBone
from math import pow
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones.stringBone import LanguageWrapper
import logging


class numericBone(baseBone):
	"""
		Holds numeric values.
		Can be used for ints and floats.
		For floats, the precision can be specified in decimal-places.
	"""

	@staticmethod
	def generageSearchWidget(target, name="NUMERIC BONE", mode="range"):
		return ({"name": name, "mode": mode, "target": target, "type": "numeric"})

	type = "numeric"

	def __init__(self, precision=0, min=-int(pow(2, 30)), max=int(pow(2, 30)), defaultValue=None, *args, **kwargs):
		"""
			Initializes a new NumericBone.

			:param precision: How may decimal places should be saved. Zero casts the value to int instead of float.
			:type precision: int
			:param min: Minimum accepted value (including).
			:type min: float
			:param max: Maximum accepted value (including).
			:type max: float
		"""
		super(numericBone, self).__init__(defaultValue=defaultValue, *args, **kwargs)
		self.precision = precision
		if not self.precision and "mode" in kwargs and kwargs["mode"] == "float":  # Fallback for old API
			self.precision = 8
		self.min = min
		self.max = max

	def isInvalid(self, value):
		if value != value:  # NaN
			return "NaN not allowed"

	def singleValueFromClient(self, value, skel, name, origData):
		try:
			rawValue = str(value).replace(",", ".", 1)
		except:
			return self.getDefaultValue(skel), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid Value")]
		else:
			if self.precision and (str(rawValue).replace(".", "", 1).replace("-", "", 1).isdigit()) and float(
					rawValue) >= self.min and float(rawValue) <= self.max:
				value = round(float(rawValue), self.precision)
			elif not self.precision and (str(rawValue).replace("-", "", 1).isdigit()) and int(
					rawValue) >= self.min and int(rawValue) <= self.max:
				value = int(rawValue)
			else:
				return self.getDefaultValue(skel), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid Value")]
		err = self.isInvalid(value)
		if err:
			return self.getDefaultValue(skel), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, err)]
		return value, None


	def buildDBFilter(self, name, skel, dbFilter, rawFilter, prefix=None):
		updatedFilter = {}
		for parmKey, paramValue in rawFilter.items():
			if parmKey.startswith(name):
				if parmKey != name and not parmKey.startswith(name + "$"):
					# It's just another bone which name start's with our's
					continue
				try:
					if not self.precision:
						paramValue = int(paramValue)
					else:
						paramValue = float(paramValue)
				except ValueError:
					# The value we should filter by is garbage, cancel this query
					logging.warning("Invalid filtering! Unparsable int/float supplied to numericBone %s" % name)
					raise RuntimeError()
				updatedFilter[parmKey] = paramValue
		return super(numericBone, self).buildDBFilter(name, skel, dbFilter, updatedFilter, prefix)

	def getSearchTags(self, valuesCache, name):
		res = set()
		value = valuesCache[name]
		if not value:
			return res
		if self.languages and isinstance(value, dict):
			if self.multiple:
				for lang in value.values():
					if not lang:
						continue
					for val in lang:
						res.add(str(val))
			else:
				for lang in value.values():
					res.add(str(lang))
		else:
			if self.multiple:
				for val in value:
					res.add(str(val))
			else:
				res.add(str(value))
		return res
