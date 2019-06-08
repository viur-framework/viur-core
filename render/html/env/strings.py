# -*- coding: utf-8 -*-
from server.render.html.utils import jinjaGlobalFunction, jinjaGlobalFilter
import json


@jinjaGlobalFilter
def parseJSON(render, s):
	"""
	Jinja2 filter: Parses a JSON-string into a dict.

	:param s: The string to be parsed.
	:type s: str

	:return: The parsed dict object. \
				Returns None if no JSON could be parsed.
	:rtype: dict
	"""
	try:
		ret = json.loads(s)
	except ValueError:
		ret = None

	return ret
