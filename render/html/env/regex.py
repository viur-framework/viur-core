# -*- coding: utf-8 -*-
from server.render.html.utils import jinjaGlobalFunction
import re


@jinjaGlobalFunction
def regexMatch(render, pattern, string, flags=0):
	"""
	Jinja2 global: Match a string for regular expression pattern.
	This function internally runs re.match().

	:param s: String where to be searched in.
	:type s: str

	:param pattern: Regular expression pattern to be matched.
	:type pattern: str

	:param flags: Flags to be passed to re.search().
	:type flags: int

	:return: A matching object on success, else None.
	:rtype: ``re.MatchObject``
	"""
	return re.match(pattern, string)


@jinjaGlobalFunction
def regexReplace(render, s, pattern, replace):
	"""
	Jinja2 global: Replace string by regular expression pattern.

	:param s: String to be replaced.
	:type s: str

	:param pattern: Regular expression pattern to be matched.
	:type pattern: str

	:param replace: Replacement string to be inserted for every matching pattern.
	:type replace: str

	:return: The string with the replaced matches.
	:rtype: str
	"""
	return re.sub(pattern, replace, s)


@jinjaGlobalFunction
def regexSearch(render, s, pattern, flags=0):
	"""
	Jinja2 global: Search a string for regular expression pattern.
	This function internally runs re.search().

	:param s: String where to be searched in.
	:type s: str

	:param pattern: Regular expression pattern to be matched.
	:type pattern: str

	:param flags: Flags to be passed to re.search().
	:type flags: int

	:return: A matching object on success, else None.
	:rtype: ``re.MatchObject``
	"""
	return re.search(pattern, s, flags)
