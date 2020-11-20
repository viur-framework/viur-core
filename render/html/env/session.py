# -*- coding: utf-8 -*-
from viur.core.render.html.utils import jinjaGlobalFunction
from viur.core.utils import currentSession


@jinjaGlobalFunction
def getSession(render):
	"""
	Jinja2 global: Allows templates to store variables server-side inside the session.

	Note: This is done in a separated part of the session for security reasons.

	:returns: A dictionary of session variables.
	:rtype: dict
	"""
	currSess = currentSession.get()
	if not currSess.get("JinjaSpace"):
		currSess["JinjaSpace"] = {}
	return currSess.get("JinjaSpace")


@jinjaGlobalFunction
def setSession(render, name, value):
	"""
	Jinja2 global: Allows templates to store variables on server-side inside the session.

	Note: This is done in a separated part of the session for security reasons.

	:param name: Name of the key
	:type name: str

	:param value: Value to store with name.
	:type value: any
	"""
	sessionData = getSession(render)
	sessionData[name] = value
	currSess = currentSession.get()
	currSess["JinjaSpace"] = sessionData
	currSess.markChanged()
