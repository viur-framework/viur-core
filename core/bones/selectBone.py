from collections import OrderedDict
from numbers import Number
from typing import Callable, Dict, List, Tuple, Union

from viur.core.bones import baseBone
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.i18n import translate

SelectBoneValue = Union[str, Number]
SelectBoneMultiple = List[SelectBoneValue]


class selectBone(baseBone):
	type = "select"

	def __init__(
		self,
		*,
		defaultValue: Union[None, Dict[str, Union[SelectBoneMultiple, SelectBoneValue]], SelectBoneMultiple] = None,
		values: Union[Dict, List, Tuple, Callable] = (),
		**kwargs
	):
		"""
			Creates a new selectBone.

			:param defaultValue: key(s) which will be checked by default
			:param values: dict of key->value pairs from which the user can choose from.
		"""
		super().__init__(defaultValue=defaultValue, **kwargs)

		# handle list/tuple as dicts
		if isinstance(values, (list, tuple)):
			values = {i: translate(i) for i in values}

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
