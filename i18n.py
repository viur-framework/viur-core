# -*- coding: utf-8 -*-

from viur.core.utils import currentRequest, currentLanguage
from viur.core.config import conf
from viur.core import db
from jinja2.ext import Extension, nodes

systemTranslations = {}


class translate:
	__slots__ = ["key", "defaultText", "hint", "translationCache"]

	def __init__(self, key, defaultText=None, hint=None):
		super(translate, self).__init__()
		self.key = key.lower()
		self.defaultText = defaultText
		self.hint = hint
		self.translationCache = None

	def __repr__(self):
		return "<translate object for %s>" % self.key

	def __str__(self):
		if self.translationCache is None:
			global systemTranslations
			self.translationCache = systemTranslations.get(self.key, {})
		try:
			lang = currentRequest.get().language
		except:
			return self.defaultText or self.key
		if lang in conf["viur.languageAliasMap"]:
			lang = conf["viur.languageAliasMap"][lang]
		if not lang in self.translationCache:
			return self.defaultText or self.key
		trStr = self.translationCache.get(lang, "")
		return trStr

	def translate(self, **kwargs):
		res = str(self)
		for k, v in kwargs.items():
			res = res.replace("{{%s}}" % k, str(v))
		return res


class TranslationExtension(Extension):
	tags = {"translate"}

	def parse(self, parser):
		# Parse the translate tag
		global systemTranslations
		args = []
		kwargs = {}
		lineno = parser.stream.current.lineno
		# Parse arguments (args and kwargs) until the current block ends
		while parser.stream.current.type != 'block_end':
			lastToken = parser.parse_expression()
			if parser.stream.current.type == "comma":  # It's an arg
				args.append(lastToken.value)
				next(parser.stream)  # Advance pointer
				continue
			elif parser.stream.current.type == "assign":
				next(parser.stream)  # Advance beyond =
				expr = parser.parse_expression()
				kwargs[lastToken.name] = expr.value
				if parser.stream.current.type == "comma":
					next(parser.stream)
				elif parser.stream.current.type == "block_end":
					break
				else:
					raise SyntaxError()
		if not 0 < len(args) < 3:
			raise SyntaxError("Translation-Key missing!")
		args += [""] * (3 - len(args))
		args += [kwargs]
		trKey = args[0]
		trDict = systemTranslations.get(trKey, {})
		args = [nodes.Const(x) for x in args]
		args.append(nodes.Const(trDict))
		return nodes.CallBlock(self.call_method("_translate", args), [], [], []).set_lineno(lineno)

	def _translate(self, key, defaultText, hint, kwargs, trDict, caller):
		# Perform the actual translation during render
		lng = currentLanguage.get()
		if lng in trDict:
			return trDict[lng].format(kwargs)
		return str(defaultText).format(kwargs)


def initializeTranslations():
	global systemTranslations
	invertMap = {}
	for srcLang, dstLang in conf["viur.languageAliasMap"].items():
		if dstLang not in invertMap:
			invertMap[dstLang] = []
		invertMap[dstLang].append(srcLang)
	for tr in db.Query("viur-translations").run(9999):
		trDict = {}
		for lang, translation in tr["translations"].items():
			trDict[lang] = translation
			if lang in invertMap:
				for v in invertMap[lang]:
					trDict[v] = translation
		systemTranslations[tr["key"]] = trDict
