# -*- coding: utf-8 -*-
from viur.core.bones.bone import baseBone
from viur.core.db import Entity, KeyClass
from viur.core.utils import normalizeKey

class keyBone(baseBone):
	type = "key"

	def __init__(self, descr="Key", readOnly=True, visible=False, **kwargs):
		super(keyBone, self).__init__(descr=descr, readOnly=True, visible=visible, defaultValue=None, **kwargs)


	def unserialize(self, skeletonValues: 'viur.core.skeleton.SkeletonValues', name: str) -> bool:
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.
			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:param expando: An instance of the dictionary-like db.Entity class
			:type expando: db.Entity
			:returns: bool
		"""
		if name == "key" and isinstance(skeletonValues.entity, Entity) and skeletonValues.entity.key and not skeletonValues.entity.key.is_partial:
			skeletonValues.accessedValues[name] = skeletonValues.entity.key
			return True
		elif name in skeletonValues.entity:
			val = skeletonValues.entity[name]
			if isinstance(val, str):
				try:
					val = normalizeKey(KeyClass.from_legacy_urlsafe(val))
				except:
					val = None
			elif not isinstance(val, KeyClass):
				val = None
			skeletonValues.accessedValues[name] = val
			return True
		return False

