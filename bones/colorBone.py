# -*- coding: utf-8 -*-
from viur.core.bones import baseBone
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
import logging


class colorBone(baseBone):
	type = "color"

	def __init__(self, mode="rgb", *args, **kwargs):  # mode rgb/rgba
		baseBone.__init__(self, *args, **kwargs)
		assert mode in {"rgb", "rgba"}
		self.mode = mode

	def fromClient(self, skel, name, data):
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
		if not name in data:
			return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, name, "Field not submitted")]
		value = data[name]
		if not value:
			return [ReadFromClientError(ReadFromClientErrorSeverity.Empty, name, "No value selected")]
		value = value.lower()
		if value.count("#") > 1:
			return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid value entered")]
		for char in value:
			if not char in "#0123456789abcdef":
				return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid value entered")]
		if self.mode == "rgb":
			if len(value) == 3:
				value = "#" + value
			if len(value) == 4:
				value = value[0:2] + value[1] + 2 * value[2] + 2 * value[3]
			if len(value) == 6 or len(value) == 7:
				if len(value) == 6:
					value = "#" + value
			else:
				return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid value entered")]
		if self.mode == "rgba":
			if len(value) == 8 or len(value) == 9:
				if len(value) == 8:
					value = "#" + value
			else:
				return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid value entered")]
		err = self.isInvalid(value)
		if err:
			return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, err)]
		skel[name] = value
