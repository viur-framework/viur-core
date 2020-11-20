# -*- coding: utf-8 -*-
from viur.core.bones.relationalBone import relationalBone
from viur.core.config import conf


class userBone(relationalBone):
	kind = "user"
	datafields = ["name"]

	def __init__(self, creationMagic=False, updateMagic=False, visible=None, multiple=False, readOnly=False, *args, **kwargs):
		if creationMagic or updateMagic:
			readOnly = False
			if visible is None:
				visible = False  # defaults
		elif visible is None:
			visible = True
		super(userBone, self).__init__(multiple=multiple, visible=visible, readOnly=readOnly, *args, **kwargs)
		self.creationMagic = creationMagic
		self.updateMagic = updateMagic
		if self.multiple and (creationMagic or updateMagic):
			raise ValueError("Cannot be multiple and have a creation/update-magic set!")

	def performMagic(self, skel, key, isAdd, *args, **kwargs):
		if self.updateMagic or (self.creationMagic and isAdd):
			user = conf["viur.mainApp"].user.getCurrentUser()
			if user:
				return self.setBoneValue(skel, key, user["key"], False)
			return self.setBoneValue(skel, key, None, False)
