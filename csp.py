# -*- coding: utf-8 -*-

"""
	This module helps configuring and reporting of content security policy rules and violations.
	To enable CSP, call addRule() from your projects main file before calling server.setup().

	Example usage::

		csp.addRule("default-src","self","enforce") #Enable CSP for all types and made us the only allowed source

		csp.addRule("style-src","self","enforce") # Start a new set of rules for stylesheets whitelist us
		csp.addRule("style-src","unsafe-inline","enforce") # This is currently needed for textBones!

	If you don't want these rules to be enforced and just getting a report of violations replace "enforce" with
	"monitor". To add a report-url use something like::

		csp.addRule("report-uri","/cspReport","enforce")

	and register a function at /cspReport to handle the reports.

	..note::

		Our tests showed that enabling a report-url on production systems has limited use. There are literally
		thousands of browser-extensions out there that inject code into the pages displayed. This causes a whole
		flood of violations-spam to your report-url.

"""

from server.config import conf
import logging

def addRule(objectType, srcOrDirective, enforceMode="monitor"):
	"""
		Adds a new rule to the CSP
		@param objectType: For which type of objects should this directive be enforced? (script-src, img-src, ...)
		@type objectType: string
		@param srcOrDirective: Either a domain which should be white-listed or a CSP-Keyword like 'self', 'unsafe-inline', etc.
		@type srcOrDirective: string
		@param enforceMode: Should this directive be enforced or just logged?
		@type enforceMode: 'monitor' or 'enforce'
	"""
	assert enforceMode in ["monitor", "enforce"], "enforceMode must be 'monitor' or 'enforce'!"
	assert objectType in [  "default-src", "script-src", "object-src", "style-src", "img-src", "media-src",
				"frame-src", "font-src", "connect-src", "report-uri"]
	assert conf["viur.mainApp"] is None, "You cannot modify CSP rules after server.buildApp() has been run!"
	assert not any(
		[x in srcOrDirective for x in [";", "'", "\"", "\n", ","]]), "Invalid character in srcOrDirective!"
	if conf["viur.contentSecurityPolicy"] is None:
		conf["viur.contentSecurityPolicy"] = {"_headerCache": {}}
	if not enforceMode in conf["viur.contentSecurityPolicy"].keys():
		conf["viur.contentSecurityPolicy"][enforceMode] = {}
	if objectType == "report-uri":
		conf["viur.contentSecurityPolicy"][enforceMode]["report-uri"] = [srcOrDirective]
	else:
		if not objectType in conf["viur.contentSecurityPolicy"][enforceMode].keys():
			conf["viur.contentSecurityPolicy"][enforceMode][objectType] = []
		conf["viur.contentSecurityPolicy"][enforceMode][objectType].append(srcOrDirective)
	rebuildHeaderCache()


def rebuildHeaderCache():
	"""
		Rebuilds the internal conf["viur.contentSecurityPolicy"]["_headerCache"] dictionary, ie. it constructs
		the Content-Security-Policy-Report-Only and Content-Security-Policy headers based on what has been passed
		to 'addRule' earlier on. Should not be called directly.
	"""
	conf["viur.contentSecurityPolicy"]["_headerCache"] = {}
	for enforceMode in ["monitor", "enforce"]:
		resStr = ""
		if not enforceMode in conf["viur.contentSecurityPolicy"].keys():
			continue
		for key, values in conf["viur.contentSecurityPolicy"][enforceMode].items():
			resStr += key
			for value in values:
				resStr += " "
				if value in ["self", "unsafe-inline", "unsafe-eval"]:
					resStr += "'%s'" % value
				else:
					resStr += value
			resStr += "; "
		if enforceMode == "monitor":
			conf["viur.contentSecurityPolicy"]["_headerCache"][
				"Content-Security-Policy-Report-Only"] = resStr
		else:
			conf["viur.contentSecurityPolicy"]["_headerCache"]["Content-Security-Policy"] = resStr
