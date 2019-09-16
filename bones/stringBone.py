# -*- coding: utf-8 -*-
from server.bones import baseBone
from server.config import conf
from server import db
from server import request
from server import utils
from server.session import current as currentSession
from server.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity
import logging
from typing import List


class LanguageWrapper(dict):
	"""
		Wrapper-class for a multi-language value.
		Its a dictionary, allowing accessing each stored language,
		but can also be used as a string, in which case it tries to
		guess the correct language.
	"""

	def __init__(self, languages):
		super(LanguageWrapper, self).__init__()
		self.languages = languages

	def __str__(self):
		return (str(self.resolve()))

	def resolve(self):
		"""
			Causes this wrapper to evaluate to the best language available for the current request.

			:returns: str|list of str
			:rtype: str|list of str
		"""
		lang = request.current.get().language  # currentSession.getLanguage()
		if not lang:
			lang = self.languages[0]
		else:
			if lang in conf["viur.languageAliasMap"]:
				lang = conf["viur.languageAliasMap"][lang]
		if lang in self and self[lang] is not None and str(
				self[lang]).strip():  # The users language is available :)
			return (self[lang])
		else:  # We need to select another lang for him
			for lang in self.languages:
				if lang in self and self[lang]:
					return (self[lang])
		return ("")


class stringBone(baseBone):
	type = "str"

	@staticmethod
	def generageSearchWidget(target, name="STRING BONE", mode="equals"):
		return ({"name": name, "mode": mode, "target": target, "type": "string"})

	def __init__(self, caseSensitive=True, languages=None, defaultValue=None, *args, **kwargs):
		super(stringBone, self).__init__(defaultValue=defaultValue, *args, **kwargs)
		self.caseSensitive = caseSensitive
		if not (languages is None or (isinstance(languages, list) and len(languages) > 0 and all(
				[isinstance(x, str) for x in languages]))):
			raise ValueError("languages must be None or a list of strings")
		self.languages = languages
		if defaultValue is None:
			if self.languages:
				self.defaultValue = LanguageWrapper(self.languages)
			else:
				self.defaultValue = ""

	def serialize(self, valuesCache, name, entity):
		for k in list(entity.keys()):  # Remove any old data
			if k.startswith("%s." % name) or k == name:
				del entity[k]
		if name not in valuesCache:
			entity[name] = self.getDefaultValue()
			return entity
		if not self.languages:
			if self.caseSensitive:
				return (super(stringBone, self).serialize(valuesCache, name, entity))
			else:
				if name != "key":
					entity[name] = valuesCache[name]
					if valuesCache[name] is None:
						entity[name + "_idx"] = None
					elif isinstance(valuesCache[name], list):
						entity[name + "_idx"] = [str(x).lower() for x in valuesCache[name]]
					else:
						entity[name + "_idx"] = str(valuesCache[name]).lower()
		else:  # Write each language separately
			if not valuesCache.get(name, None):
				return entity
			if isinstance(valuesCache[name], str) or (
					isinstance(valuesCache[name], list) and self.multiple):  # Convert from old format
				lang = self.languages[0]
				entity["%s_%s" % (name, lang)] = valuesCache[name]
				if not self.caseSensitive:
					if isinstance(valuesCache[name], str):
						entity["%s_%s_idx" % (name, lang)] = valuesCache[name].lower()
					else:
						entity["%s_%s_idx" % (name, lang)] = [x.lower for x in valuesCache[name]]
				# Fill in None for all remaining languages (needed for sort!)
				for lang in self.languages[1:]:
					entity["%s_%s" % (name, lang)] = ""
					if not self.caseSensitive:
						entity["%s_%s_idx" % (name, lang)] = ""
			else:
				assert isinstance(valuesCache[name], dict)
				entity[name] = valuesCache[name]
				if not self.caseSensitive:
					if self.multiple:
						entity["%s_idx" % name] = {k: [x.lower() for x in v] for k, v in valuesCache[name].items()}
					else:
						entity["%s_idx" % name] = {k: v.lower() for k, v in valuesCache[name].items()}
			# FIXME:
			#	# Fill in None for all remaining languages (needed for sort!)
			#	entity["%s_%s" % (name, lang)] = ""
			#	if not self.caseSensitive:
			#		entity["%s_%s_idx" % (name, lang)] = ""
		return entity

	def unserialize(self, valuesCache, name, expando):
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.

			:param name: The property-name this bone has in its :class:`server.skeleton.Skeleton` (not the description!)
			:type name: str
			:param expando: An instance of the dictionary-like db.Entity class
			:type expando: :class:`server.db.Entity`
		"""
		if not self.languages:
			valuesCache[name] = expando.get(name)
		else:
			valuesCache[name] = LanguageWrapper(self.languages)
			storedVal = expando.get(name)
			if isinstance(storedVal, dict):
				valuesCache[name].update(storedVal)
			# FIXME:
			# if isinstance(val, list) and not self.multiple:
			#	val = ", ".join(val)
			elif isinstance(storedVal, str):  # Old (non-multi-lang) format
				valuesCache[name][self.languages[0]] = storedVal
		return True

	def fromClient(self, valuesCache, name, data):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this rawValue and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.

			:param name: Our name in the :class:`server.skeleton.Skeleton`
			:type name: str
			:param data: *User-supplied* request-data
			:type data: dict
			:returns: str or None
		"""
		if not name in data and not any(x.startswith("%s." % name) for x in data):
			return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, name, "Field not submitted")]
		res = None
		errors = []
		if self.multiple and self.languages:
			res = LanguageWrapper(self.languages)
			for lang in self.languages:
				res[lang] = []
				if "%s.%s" % (name, lang) in data:
					val = data["%s.%s" % (name, lang)]
					if isinstance(val, str):
						err = self.isInvalid(val)
						if not err:
							res[lang].append(utils.escapeString(val))
						else:
							errors.append(
								ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, err)
							)
					elif isinstance(val, list):
						for v in val:
							err = self.isInvalid(v)
							if not err:
								res[lang].append(utils.escapeString(v))
							else:
								errors.append(
									ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, err)
								)
			if not any(res.values()) and not errors:
				errors.append(
					ReadFromClientError(ReadFromClientErrorSeverity.Empty, name, "No rawValue entered")
				)
		elif self.multiple and not self.languages:
			rawValue = data.get(name)
			res = []
			if not rawValue:
				errors.append(
					ReadFromClientError(ReadFromClientErrorSeverity.Empty, name, "No rawValue entered")
				)
			else:
				if not isinstance(rawValue, list):
					rawValue = [rawValue]
				for val in rawValue:
					err = self.isInvalid(val)
					if not err:
						res.append(utils.escapeString(val))
					else:
						errors.append(
							ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, err)
						)
				if len(res) > 0:
					res = res[0:254]  # Max 254 character
				else:
					errors.append(
						ReadFromClientError(ReadFromClientErrorSeverity.Empty, name, "No valid rawValue entered")
					)
		elif not self.multiple and self.languages:
			res = LanguageWrapper(self.languages)
			for lang in self.languages:
				if "%s.%s" % (name, lang) in data:
					val = data["%s.%s" % (name, lang)]
					err = self.isInvalid(val)
					if not err:
						res[lang] = utils.escapeString(val)
					else:
						errors.append(
							ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, err)
						)
			if len(res.keys()) == 0 and not errors:
				errors.append(
					ReadFromClientError(ReadFromClientErrorSeverity.Empty, name, "No rawValue entered")
				)
		else:
			rawValue = data.get(name)
			err = self.isInvalid(rawValue)
			if not err:
				res = utils.escapeString(rawValue)
			else:
				errors.append(
					ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, err)
				)
			if not rawValue and not errors:
				errors.append(
					ReadFromClientError(ReadFromClientErrorSeverity.Empty, name, "No rawValue entered")
				)
		valuesCache[name] = res
		if errors:
			return errors

	def buildDBFilter(self, name, skel, dbFilter, rawFilter, prefix=None):
		if not name in rawFilter and not any(
				[(x.startswith(name + "$") or x.startswith(name + ".")) for x in rawFilter.keys()]):
			return (super(stringBone, self).buildDBFilter(name, skel, dbFilter, rawFilter, prefix))
		hasInequalityFilter = False
		if not self.languages:
			namefilter = name
		else:
			lang = None
			for key in rawFilter.keys():
				if key.startswith("%s." % name):
					langStr = key.replace("%s." % name, "")
					if langStr in self.languages:
						lang = langStr
						break
			if not lang:
				lang = request.current.get().language  # currentSession.getLanguage()
				if not lang or not lang in self.languages:
					lang = self.languages[0]
			namefilter = "%s.%s" % (name, lang)
		if name + "$lk" in rawFilter:  # Do a prefix-match
			if not self.caseSensitive:
				dbFilter.filter((prefix or "") + namefilter + "_idx >=", str(rawFilter[name + "$lk"]).lower())
				dbFilter.filter((prefix or "") + namefilter + "_idx <",
								str(rawFilter[name + "$lk"] + u"\ufffd").lower())
			else:
				dbFilter.filter((prefix or "") + namefilter + " >=", str(rawFilter[name + "$lk"]))
				dbFilter.filter((prefix or "") + namefilter + " < ", str(rawFilter[name + "$lk"] + u"\ufffd"))
			hasInequalityFilter = True
		if name + "$gt" in rawFilter:  # All entries after
			if not self.caseSensitive:
				dbFilter.filter((prefix or "") + namefilter + "_idx >", str(rawFilter[name + "$gt"]).lower())
			else:
				dbFilter.filter((prefix or "") + namefilter + " >", str(rawFilter[name + "$gt"]))
			hasInequalityFilter = True
		if name + "$lt" in rawFilter:  # All entries before
			if not self.caseSensitive:
				dbFilter.filter((prefix or "") + namefilter + "_idx <", str(rawFilter[name + "$lt"]).lower())
			else:
				dbFilter.filter((prefix or "") + namefilter + " <", str(rawFilter[name + "$lt"]))
			hasInequalityFilter = True
		if name in rawFilter:  # Normal, strict match
			if not self.caseSensitive:
				dbFilter.filter((prefix or "") + namefilter + "_idx", str(rawFilter[name]).lower())
			else:
				dbFilter.filter((prefix or "") + namefilter, str(rawFilter[name]))
		return (dbFilter)

	def buildDBSort(self, name, skel, dbFilter, rawFilter):
		if "orderby" in rawFilter and (rawFilter["orderby"] == name or (
				isinstance(rawFilter["orderby"], str) and rawFilter["orderby"].startswith(
			"%s." % name) and self.languages)):
			if self.languages:
				lang = None
				if rawFilter["orderby"].startswith("%s." % name):
					lng = rawFilter["orderby"].replace("%s." % name, "")
					if lng in self.languages:
						lang = lng
				if lang is None:
					lang = request.current.get().language  # currentSession.getLanguage()
					if not lang or not lang in self.languages:
						lang = self.languages[0]
				if self.caseSensitive:
					prop = "%s.%s" % (name, lang)
				else:
					prop = "%s.%s_idx" % (name, lang)
			else:
				if self.caseSensitive:
					prop = name
				else:
					prop = name + "_idx"
			if "orderdir" in rawFilter and rawFilter["orderdir"] == "1":
				order = (prop, db.DESCENDING)
			else:
				order = (prop, db.ASCENDING)
			inEqFilter = [x for x in dbFilter.datastoreQuery.keys() if
						  (">" in x[-3:] or "<" in x[-3:] or "!=" in x[-4:])]
			if inEqFilter:
				inEqFilter = inEqFilter[0][: inEqFilter[0].find(" ")]
				if inEqFilter != order[0]:
					logging.warning("I fixed you query! Impossible ordering changed to %s, %s" % (inEqFilter, order[0]))
					dbFilter.order(inEqFilter, order)
				else:
					dbFilter.order(order)
			else:
				dbFilter.order(order)
		return (dbFilter)

	def getSearchTags(self, valuesCache, name):
		res = []
		if not valuesCache.get(name):
			return (res)
		value = valuesCache[name]
		if self.languages and isinstance(value, dict):
			if self.multiple:
				for lang in value.values():
					if not lang:
						continue
					for val in lang:
						for line in str(val).splitlines():
							for key in line.split(" "):
								key = "".join([c for c in key if c.lower() in conf[
									"viur.searchValidChars"]])
								if key and key not in res and len(key) > 1:
									res.append(key.lower())
			else:
				for lang in value.values():
					for line in str(lang).splitlines():
						for key in line.split(" "):
							key = "".join([c for c in key if
										   c.lower() in conf["viur.searchValidChars"]])
							if key and key not in res and len(key) > 1:
								res.append(key.lower())
		else:
			if self.multiple:
				for val in value:
					for line in str(val).splitlines():
						for key in line.split(" "):
							key = "".join([c for c in key if
										   c.lower() in conf["viur.searchValidChars"]])
							if key and key not in res and len(key) > 1:
								res.append(key.lower())
			else:
				for line in str(value).splitlines():
					for key in line.split(" "):
						key = "".join(
							[c for c in key if c.lower() in conf["viur.searchValidChars"]])
						if key and key not in res and len(key) > 1:
							res.append(key.lower())

		return (res)

	def getSearchDocumentFields(self, valuesCache, name, prefix=""):
		"""
			Returns a list of search-fields (GAE search API) for this bone.
		"""
		res = []
		if self.languages:
			if valuesCache.get(name) is not None:
				for lang in self.languages:
					if lang in valuesCache[name]:
						res.append(
							search.TextField(name=prefix + name, value=str(valuesCache[name][lang]), language=lang))
		else:
			res.append(search.TextField(name=prefix + name, value=str(valuesCache[name])))

		return res

	def getUniquePropertyIndexValues(self, valuesCache: dict, name: str) -> List[str]:
		if self.languages:
			# Not yet implemented as it's unclear if we should keep each language distinct or not
			raise NotImplementedError
		return super(stringBone, self).getUniquePropertyIndexValues(valuesCache, name)
