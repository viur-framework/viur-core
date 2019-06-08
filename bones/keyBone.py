# -*- coding: utf-8 -*-
from server.bones.bone import baseBone
from server.utils import normalizeKey


class keyBone(baseBone):
	kind = "key"

	def __init__(self, descr="Key", readOnly=True, visible=False, **kwargs):
		super(keyBone, self).__init__(descr=descr, readOnly=readOnly, visible=visible, **kwargs)

	def refresh(self, valuesCache, boneName, skel):
		"""
			Refresh all values we might have cached from other entities.
		"""
		if boneName in valuesCache and valuesCache[boneName]:
			valuesCache[boneName] = normalizeKey(valuesCache[boneName])
