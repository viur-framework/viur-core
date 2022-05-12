from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from typing import List, Union, Any
import logging


class BooleanBone(BaseBone):
	type = "bool"
	trueStrs = [str(True), u"1", u"yes"]

	def __init__(
		self,
		*,
		defaultValue: bool = False,
		**kwargs
	):
		if defaultValue not in (True, False):
			raise ValueError("Only 'True' or 'False' can be provided as BooleanBone defaultValue")

		super().__init__(defaultValue=defaultValue, **kwargs)

	def singleValueFromClient(self, value, skel, name, origData):
		if str(value) in self.trueStrs:
			return True, None
		else:
			return False, None

	def getEmptyValue(self):
		return False

	def isEmpty(self, rawValue: Any):
		if rawValue is self.getEmptyValue():
			return True
		return not bool(rawValue)

	def refresh(self, skel, boneName) -> None:
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
		if not isinstance(skel[boneName], bool):
			val = skel[boneName]
			if str(val) in self.trueStrs:
				skel[boneName] = True
			else:
				skel[boneName] = False

	def buildDBFilter(self, name, skel, dbFilter, rawFilter, prefix=None):
		if name in rawFilter:
			val = rawFilter[name]
			if str(val) in self.trueStrs:
				val = True
			else:
				val = False
			return super().buildDBFilter(name, skel, dbFilter, {name: val}, prefix=prefix)

		return dbFilter
