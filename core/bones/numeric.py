from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
import logging, warnings
from math import pow
from typing import Any, Union


class NumericBone(BaseBone):
	"""
		Holds numeric values.
		Can be used for ints and floats.
		For floats, the precision can be specified in decimal-places.
	"""
	type = "numeric"

	def __init__(
		self,
		*,
		max: Union[int, float] = int(pow(2, 30)),
		min: Union[int, float] = -int(pow(2, 30)),
		mode=None,  # deprecated!
		precision: int = 0,
		**kwargs
	):
		"""
			Initializes a new NumericBone.

			:param precision: How may decimal places should be saved. Zero casts the value to int instead of float.
			:type precision: int
			:param min: Minimum accepted value (including).
			:type min: float
			:param max: Maximum accepted value (including).
			:type max: float
		"""
		super().__init__(**kwargs)

		if mode:
			logging.warning("mode-parameter to NumericBone is deprecated")
			warnings.warn(
				"mode-parameter to NumericBone is deprecated", DeprecationWarning
			)

		if not precision and mode == "float":
			logging.warning("mode='float' is deprecated, use precision=8 for same behavior")
			warnings.warn(
				"mode='float' is deprecated, use precision=8 for same behavior", DeprecationWarning
			)
			precision = 8

		self.precision = precision
		self.min = min
		self.max = max

	def isInvalid(self, value):
		if value != value:  # NaN
			return "NaN not allowed"

	def getEmptyValue(self):
		if self.precision:
			return 0.0
		else:
			return 0

	def isEmpty(self, rawValue: Any):
		if isinstance(rawValue, str) and not rawValue:
			return True
		try:
			if self.precision:
				if isinstance(rawValue, str):
					rawValue = rawValue.replace(",", ".", 1)
				rawValue = float(rawValue)
			else:
				rawValue = int(rawValue)
		except:
			return True
		return rawValue == self.getEmptyValue()

	def singleValueFromClient(self, value, skel, name, origData):
		try:
			rawValue = str(value).replace(",", ".", 1)
		except:
			return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid Value")]
		else:
			if self.precision and (str(rawValue).replace(".", "", 1).replace("-", "", 1).isdigit()) and float(
				rawValue) >= self.min and float(rawValue) <= self.max:
				value = round(float(rawValue), self.precision)
			elif not self.precision and (str(rawValue).replace("-", "", 1).isdigit()) and int(
				rawValue) >= self.min and int(rawValue) <= self.max:
				value = int(rawValue)
			else:
				return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid Value")]
		err = self.isInvalid(value)
		if err:
			return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
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
					logging.warning("Invalid filtering! Unparsable int/float supplied to NumericBone %s" % name)
					raise RuntimeError()
				updatedFilter[parmKey] = paramValue

		return super().buildDBFilter(name, skel, dbFilter, updatedFilter, prefix)

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
