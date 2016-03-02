# -*- coding: utf-8 -*-
from server.render.jinja2.utils import jinjaGlobal, jinjaFilter
import json

@jinjaFilter
def clearString(s, words):
	"""
	Jinja2 filter: Remove words from a string.

	:param s: Input string to be modified.
	:type s: str

	:param words: List of words to be removed from ``s``.
	:type words: list of str

	:return: The modified string.
	:rtype: str
	"""
	for w in words:
		s = s.replace(w, "")

	return s

@jinjaFilter
def parseJSON(s):
	"""
	Jinja2 filter: Parses a JSON-string into a dict.

	:param s: The string to be parsed.
	:type s: str

	:return: The parsed dict object. \
				Returns None if no JSON could be parsed.
	:rtype: dict
	"""
	return json.loads(s) or None
