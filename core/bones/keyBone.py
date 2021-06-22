# -*- coding: utf-8 -*-
from viur.core.bones.bone import baseBone
from viur.core.db import Entity, KeyClass, keyHelper, KEY_SPECIAL_PROPERTY
from viur.core.utils import normalizeKey
import logging


class keyBone(baseBone):
	type = "key"

	def __init__(self, descr="Key", readOnly=True, visible=False, **kwargs):
		super(keyBone, self).__init__(descr=descr, readOnly=True, visible=visible, defaultValue=None, **kwargs)

	def unserialize(self, skel: 'viur.core.skeleton.SkeletonValues', name: str) -> bool:
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

		def fixVals(val):
			if isinstance(val, str):
				try:
					val = normalizeKey(KeyClass.from_legacy_urlsafe(val))
				except:
					val = None
			elif not isinstance(val, KeyClass):
				val = None
			return val

		if name == "key" and isinstance(skel.dbEntity,
										Entity) and skel.dbEntity.key and not skel.dbEntity.key.is_partial:
			skel.accessedValues[name] = skel.dbEntity.key
			return True
		elif name in skel.dbEntity:
			val = skel.dbEntity[name]
			if isinstance(val, list):
				val = [fixVals(x) for x in val if fixVals(x)]
			else:
				val = fixVals(val)
			if self.multiple and not isinstance(val, list):
				if val:
					val = [val]
				else:
					val = []
			elif not self.multiple and isinstance(val, list):
				val = val[0]
			skel.accessedValues[name] = val
			return True
		return False

	def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
		"""
			Serializes this bone into something we
			can write into the datastore.

			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:returns: dict
		"""
		if name in skel.accessedValues:
			if name == "key":
				skel.dbEntity.key = skel.accessedValues["key"]
			else:
				skel.dbEntity[name] = skel.accessedValues[name]
				skel.dbEntity.exclude_from_indexes.discard(name)  # Keys can never be not indexed
			return True
		return False

	def buildDBFilter(self, name, skel, dbFilter, rawFilter, prefix=None):
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

		def _decodeKey(key):
			if isinstance(key, KeyClass):
				return key
			else:
				try:
					return KeyClass.from_legacy_urlsafe(key)
				except Exception as e:
					logging.exception(e)
					logging.warning("Could not decode key %s" % key)
					raise RuntimeError()

		if name in rawFilter:
			if isinstance(rawFilter[name], list):
				if isinstance(dbFilter.filters, list):
					raise ValueError("In-Filter already used!")
				elif dbFilter.filters is None:
					return dbFilter  # Query is already unsatisfiable
				oldFilter = dbFilter.filters
				dbFilter.filters = []
				for key in rawFilter[name]:
					newFilter = oldFilter.copy()
					try:
						if name == "key":
							newFilter["%s%s =" % (prefix or "", KEY_SPECIAL_PROPERTY)] = _decodeKey(key)
						else:
							newFilter["%s%s =" % (prefix or "", name)] = _decodeKey(key)
					except:  # Invalid key or something
						raise RuntimeError()
					dbFilter.filters.append(newFilter)
			else:
				try:
					if name == "key":
						dbFilter.filter("%s%s =" % (prefix or "", KEY_SPECIAL_PROPERTY), _decodeKey(rawFilter[name]))
					else:
						dbFilter.filter("%s%s =" % (prefix or "", name), _decodeKey(rawFilter[name]))
				except:  # Invalid key or something
					raise RuntimeError()
			return dbFilter
