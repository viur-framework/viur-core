# -*- coding: utf-8 -*-
from server import session
from server.render.jinja2.utils import jinjaGlobal

@jinjaGlobal
def getSession():
	"""
	Jinja2 global: Allows templates to store variables server-side inside the session.

	Note: This is done in a separated part of the session for security reasons.

	:returns: A dictionary of session variables.
	:rtype: dict
	"""
	if not session.current.get("JinjaSpace"):
		session.current["JinjaSpace"] = {}

	return session.current.get("JinjaSpace")

@jinjaGlobal
def setSession(name, value):
	"""
	Jinja2 global: Allows templates to store variables on server-side inside the session.

	Note: This is done in a separated part of the session for security reasons.

	:param name: Name of the key
	:type name: str

	:param value: Value to store with name.
	:type value: any
	"""
	sessionData = getSession()
	sessionData[name] = value
	session.current["JinjaSpace"] = sessionData
	session.current.markChanged()
