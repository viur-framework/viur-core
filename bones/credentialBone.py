# -*- coding: utf-8 -*-
from server.bones import stringBone


class credentialBone(stringBone):
	"""
		A bone for storing credentials.
		This is always empty if read from the database.
		If its saved, its ignored if its values is still empty.
		If its value is not empty, it will update the value in the database
	"""
	type = "str.credential"

	def __init__(self, *args, **kwargs):
		super(credentialBone, self).__init__(*args, **kwargs)
		if self.multiple or self.languages:
			raise ValueError("Credential-Bones cannot be multiple or translated!")

	def serialize(self, valuesCache, name, entity):
		"""
			Update the value only if a new value is supplied.
		"""
		if valuesCache.get(name) and valuesCache[name] != "":
			entity[name] = valuesCache[name]
		return entity

	def unserialize(self, valuesCache, name, values):
		"""
			We'll never read our value from the database.
		"""
		return {}
