# -*- coding: utf-8 -*-
from server.bones.selectOneBone import selectOneBone

class selectGenderBone( selectOneBone ):
	TITLES  = { "m" : "Mr.", "f" : "Mrs." }

	def __init__( self, sortBy="values", *args, **kwargs ):
		super( selectGenderBone, self ).__init__( sortBy=sortBy, *args,  **kwargs )

		self.values = self.TITLES

		if not "required" in kwargs or not kwargs[ "required" ]:
			self.values[ "" ] = ""

	def isMale(self):
		"""
		Returns True if current bone value is male.
		"""
		return self.value == "m"

	def isFemale(self):
		"""
		Returns True if current bone value is female.
		"""
		return self.value == "f"
