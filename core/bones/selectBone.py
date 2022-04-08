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

	def __init__(self, defaultValue: Union[None, Dict[str, Union[SelectBoneMultiple, SelectBoneValue]], SelectBoneMultiple] = None,
				 values: Union[Dict, List, Tuple, Callable] = (),
				 multiple: bool = False, languages: bool = False, *args, **kwargs):
		"""
			Creates a new selectBone.

			:param defaultValue: key(s) which will be checked by default
			:param values: dict of key->value pairs from which the user can choose from.
		"""
		if defaultValue is None and multiple:
			if languages:
				defaultValue = {}
			else:
				defaultValue = []

		super(selectBone, self).__init__(
			defaultValue=defaultValue, multiple=multiple, languages=languages, *args, **kwargs)

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
