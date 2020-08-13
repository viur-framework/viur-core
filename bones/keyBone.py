# -*- coding: utf-8 -*-
from viur.core.bones.bone import baseBone
from viur.core.db import Entity, KeyClass, keyHelper, KEY_SPECIAL_PROPERTY
from viur.core.utils import normalizeKey
import logging

class keyBone(baseBone):
	type = "key"

	def __init__(self, descr="Key", readOnly=True, visible=False, **kwargs):
		super(keyBone, self).__init__(descr=descr, readOnly=True, visible=visible, defaultValue=None, **kwargs)

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
					return dbFilter # Query is already unsatisfiable
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
