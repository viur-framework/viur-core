from server.config import conf
import logging

"""
	This module helps configuring and reporting of content security policy rules and violations
"""

def addRule( objectType, srcOrDirective, enforceMode="monitor" ):
	"""
		Adds a new rule to the CSP
		@param objectType: For which type of objects should this directive be enforced? (script-src, img-src, ...)
		@type objectType: string
		@param srcOrDirective: Either a domain which should be white-listed or a CSP-Keyword like 'self', 'unsafe-inline', etc.
		@type srcOrDirective: string
		@param enforceMode: Should this directive be enforced or just logged?
		@type enforceMode: 'monitor' or 'enforce'
	"""
	assert enforceMode in ["monitor","enforce"], "enforceMode must be 'monitor' or 'enforce'!"
	assert objectType in ["default-src","script-src","object-src","style-src","img-src","media-src","frame-src","font-src","connect-src","report-uri"]
	assert conf["viur.mainApp"] is None, "You cannot modify CSP rules after server.buildApp() has been run!"
	assert not any( [x in srcOrDirective for x in [";", "'", "\"", "\n", ","]]), "Invalid character in srcOrDirective!"
	if conf["viur.contentSecurityPolicy"] is None:
		conf["viur.contentSecurityPolicy"] = {"_headerCache":{}}
	if not enforceMode in conf["viur.contentSecurityPolicy"].keys():
		conf["viur.contentSecurityPolicy"][ enforceMode ] = {}
	if objectType=="report-uri":
		conf["viur.contentSecurityPolicy"][ enforceMode ]["report-uri"] = srcOrDirective
	else:
		if not objectType in conf["viur.contentSecurityPolicy"][ enforceMode ].keys():
			conf["viur.contentSecurityPolicy"][ enforceMode ][ objectType ] = []
		conf["viur.contentSecurityPolicy"][ enforceMode ][ objectType ].append( srcOrDirective )
	rebuildHeaderCache()

def rebuildHeaderCache():
	"""
		Rebuilds the internal conf["viur.contentSecurityPolicy"]["_headerCache"] dictionary, ie. it constructs
		the Content-Security-Policy-Report-Only and Content-Security-Policy headers based on what has been passed to 'addRule' earlier on.
	"""
	conf["viur.contentSecurityPolicy"]["_headerCache"] = {}
	for enforceMode in ["monitor","enforce"]:
		resStr = ""
		if not enforceMode in conf["viur.contentSecurityPolicy"].keys():
			continue
		for key, values in conf["viur.contentSecurityPolicy"][enforceMode].items():
			resStr += key
			for value in values:
				resStr += " "
				if value in ["self","unsafe-inline","unsafe-eval"]:
					resStr += "'%s'" % value
				else:
					resStr += value
			resStr += "; "
		if enforceMode=="monitor":
			conf["viur.contentSecurityPolicy"]["_headerCache"]["Content-Security-Policy-Report-Only"] = resStr
		else:
			conf["viur.contentSecurityPolicy"]["_headerCache"]["Content-Security-Policy"] = resStr


