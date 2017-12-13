# -*- coding: utf-8 -*-
from server.bones.bone import baseBone
from server.utils import normalizeKey

class keyBone(baseBone):
	kind = "key"

	def __init__(self, descr="Key", readOnly=True, visible=False, normalize=True, **kwargs):
		super(keyBone, self).__init__(descr=descr, readOnly=readOnly, visible=visible, **kwargs)
		self.normalize = normalize

	def serialize(self, valuesCache, name, entity):
		if name != "key":
			entity.set(name, normalizeKey(valuesCache[name]) if self.normalize else str(valuesCache[name]), self.indexed)

		return entity

	def unserialize(self, valuesCache, name, expando):
		if name in expando:
			valuesCache[name] = normalizeKey(expando[name]) if self.normalize else str(expando[name])

		return True
