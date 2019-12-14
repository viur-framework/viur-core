# -*- coding: utf-8 -*-

from viur.core.request import current as currentRequest
from viur.core.config import conf
from viur.core import db

### Multi-Language Part
#try:
#	import translations
#
#	conf["viur.availableLanguages"].extend([x for x in dir(translations) if (len(x) == 2 and not x.startswith("_"))])
#except ImportError:  # The Project doesnt use Multi-Language features
#	translations = None

systemTranslations = {}

class translate:
	__slots__ = ["key", "defaultText","hint"]
	def __init__(self, key, defaultText=None, hint=None):
		super(translate, self).__init__()
		self.key = key.lower()
		self.defaultText = defaultText
		self.hint = hint

	def __repr__(self):
		return "<translate object for %s>" % self.key

	def __str__(self):
		try:
			lang = currentRequest.get().language
		except:
			return self.defaultText or self.key
		if lang in conf["viur.languageAliasMap"]:
			lang = conf["viur.languageAliasMap"][lang]
		if not lang in systemTranslations:
			return self.defaultText or self.key
		trDict = systemTranslations[lang]
		if not self.key in trDict:
			return self.defaultText or self.key
		return trDict[self.key]

	def translate(self, **kwargs):
		# FIXME!
		#if res is None and conf["viur.logMissingTranslations"]:
		#	from viur.core import db
		#	db.GetOrInsert(key="%s-%s" % (key, str(lang)),
		#				   kindName="viur-missing-translations",
		#				   langkey=key, lang=lang)
		res = str(self)
		for k, v in kwargs.items():
			res = res.replace("{{%s}}" % k, str(v))
		return res


def initializeTranslations():
	global systemTranslations
	for tr in db.Query("viur-translations").run(9999):
		lng = tr["language"]
		if not lng in systemTranslations:
			systemTranslations[lng] = {}
		systemTranslations[lng][tr["key"]] = tr["translation"]
