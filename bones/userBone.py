# -*- coding: utf-8 -*-
from viur.core.bones.relationalBone import relationalBone
from viur.core.config import conf


class userBone(relationalBone):
	kind = "user"
	datafields = ["name"]

	def __init__(self, creationMagic=False, updateMagic=False, visible=None, multiple=False, *args, **kwargs):

		if creationMagic or updateMagic:
			if visible is None:
				visible = False  # defaults

			multiple = False  # override

		elif visible is None:
			visible = True

		super(userBone, self).__init__(multiple=multiple, visible=visible, *args, **kwargs)

		self.creationMagic = creationMagic
		self.updateMagic = updateMagic

	def performMagic(self, skel, key, isAdd, *args, **kwargs):
		if self.updateMagic or (self.creationMagic and isAdd):
			user = conf["viur.mainApp"].user.getCurrentUser()
			if user:
				return self.setBoneValue(skel, key, user["key"], False)
			return self.setBoneValue(skel, key, None, False)
