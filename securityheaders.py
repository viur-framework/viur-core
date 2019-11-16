# -*- coding: utf-8 -*-
from viur.server.config import conf
import logging


def addCspRule(objectType, srcOrDirective, enforceMode="monitor"):
	"""
		This function helps configuring and reporting of content security policy rules and violations.
		To enable CSP, call addCspRule() from your projects main file before calling server.setup().

		Example usage::

			security.addCspRule("default-src","self","enforce") #Enable CSP for all types and made us the only allowed source

			security.addCspRule("style-src","self","enforce") # Start a new set of rules for stylesheets whitelist us
			security.addCspRule("style-src","unsafe-inline","enforce") # This is currently needed for textBones!

		If you don't want these rules to be enforced and just getting a report of violations replace "enforce" with
		"monitor". To add a report-url use something like::

			security.addCspRule("report-uri","/cspReport","enforce")

		and register a function at /cspReport to handle the reports.

		..note::

			Our tests showed that enabling a report-url on production systems has limited use. There are literally
			thousands of browser-extensions out there that inject code into the pages displayed. This causes a whole
			flood of violations-spam to your report-url.


		:param objectType: For which type of objects should this directive be enforced? (script-src, img-src, ...)
		:type objectType: str
		:param srcOrDirective: Either a domain which should be white-listed or a CSP-Keyword like 'self', 'unsafe-inline', etc.
		:type srcOrDirective: str
		:param enforceMode: Should this directive be enforced or just logged?
		:type enforceMode: 'monitor' or 'enforce'
	"""
	assert enforceMode in ["monitor", "enforce"], "enforceMode must be 'monitor' or 'enforce'!"
	assert objectType in ["default-src", "script-src", "object-src", "style-src", "img-src", "media-src",
						  "frame-src", "font-src", "connect-src", "report-uri"]
	assert conf["viur.mainApp"] is None, "You cannot modify CSP rules after server.buildApp() has been run!"
	assert not any(
		[x in srcOrDirective for x in [";", "'", "\"", "\n", ","]]), "Invalid character in srcOrDirective!"
	if conf["viur.security.contentSecurityPolicy"] is None:
		conf["viur.security.contentSecurityPolicy"] = {"_headerCache": {}}
	if not enforceMode in conf["viur.security.contentSecurityPolicy"]:
		conf["viur.security.contentSecurityPolicy"][enforceMode] = {}
	if objectType == "report-uri":
		conf["viur.security.contentSecurityPolicy"][enforceMode]["report-uri"] = [srcOrDirective]
	else:
		if not objectType in conf["viur.security.contentSecurityPolicy"][enforceMode]:
			conf["viur.security.contentSecurityPolicy"][enforceMode][objectType] = []
		if not srcOrDirective in conf["viur.security.contentSecurityPolicy"][enforceMode][objectType]:
			conf["viur.security.contentSecurityPolicy"][enforceMode][objectType].append(srcOrDirective)


def _rebuildCspHeaderCache():
	"""
		Rebuilds the internal conf["viur.security.contentSecurityPolicy"]["_headerCache"] dictionary, ie. it constructs
		the Content-Security-Policy-Report-Only and Content-Security-Policy headers based on what has been passed
		to 'addRule' earlier on. Should not be called directly.
	"""
	conf["viur.security.contentSecurityPolicy"]["_headerCache"] = {}
	for enforceMode in ["monitor", "enforce"]:
		resStr = ""
		if not enforceMode in conf["viur.security.contentSecurityPolicy"]:
			continue
		for key, values in conf["viur.security.contentSecurityPolicy"][enforceMode].items():
			resStr += key
			for value in values:
				resStr += " "
				if value in ["self", "unsafe-inline", "unsafe-eval"]:
					resStr += "'%s'" % value
				else:
					resStr += value
			resStr += "; "
		if enforceMode == "monitor":
			conf["viur.security.contentSecurityPolicy"]["_headerCache"][
				"Content-Security-Policy-Report-Only"] = resStr
		else:
			conf["viur.security.contentSecurityPolicy"]["_headerCache"]["Content-Security-Policy"] = resStr


def enableStrictTransportSecurity(maxAge=365 * 24 * 60 * 60, includeSubDomains=False, preload=False):
	"""
		Enables HTTP strict transport security.

		:param maxAge: The time, in seconds, that the browser should remember that this site is only to be accessed using HTTPS.
		:param includeSubDomains: If this parameter is set, this rule applies to all of the site's subdomains as well.
		:param preload: If set, we'll issue a hint that preloading would be appreciated.
		:return: None
	"""
	conf["viur.security.strictTransportSecurity"] = "max-age=%s" % maxAge
	if includeSubDomains:
		conf["viur.security.strictTransportSecurity"] += "; includeSubDomains"
	if preload:
		conf["viur.security.strictTransportSecurity"] += "; preload"
	pass


def setPublicKeyPins(pins, method="sha256", maxAge=2 * 24 * 60 * 60, includeSubDomains=False, reportUri=None):
	"""
		Set certificate pins. There must be at *least* two pins.
		See https://developer.mozilla.org/en/docs/Web/Security/Public_Key_Pinning for more details.
		:param pins: List of Pins
		:param method: Hash algorithm used. Must be currently sha256.
		:param maxAge: The time, in seconds, that the browser should remember that this site is only to be accessed using one of the pinned keys.
		:param includeSubDomains: If this optional parameter is specified, this rule applies to all of the site's subdomains as well.
		:param reportUri: If this optional parameter is specified, pin validation failures are reported to the given URL.
		:return: None
	"""
	for pin in pins:
		assert not any([x in pin for x in "\"\n\r;"]), "Invalid Pin: %s" % pin
	assert method in ["sha256"], "Method must be sha256 atm."
	res = " ".join(["pin-%s=\"%s\";" % (method, pin) for pin in pins])
	res += " max-age=%s" % maxAge
	if includeSubDomains:
		res += "; includeSubDomains"
	if reportUri:
		assert not any([x in reportUri for x in "\"\n\r;"]), "Invalid reportUri"
		res += "; report-uri=\"%s\"" % reportUri
	conf["viur.security.publicKeyPins"] = res


def setXFrameOptions(action, uri=None):
	"""
		Sets X-Frame-Options to prevent click-jacking attacks.
		:param action: off | deny | sameorigin | allow-from
		:type action: str
		:param uri: URL to whitelist
		:type uri: str
		:return:
	"""
	if action == "off":
		conf["viur.security.xFrameOptions"] = None
	elif action in ["deny", "sameorigin"]:
		conf["viur.security.xFrameOptions"] = (action, None)
	elif action == "allow-from":
		if uri is None or not (uri.lower().startswith("https://") or uri.lower().startswith("http://")):
			raise ValueError("If action is allow-from, an uri MUST be given and start with http(s)://")
		conf["viur.security.xFrameOptions"] = (action, uri)


def setXXssProtection(enable):
	"""
		Sets X-XSS-Protection header. If set, mode will always be block.
		:param enable: Enable the protection or not. Set to None to drop this header
		:type enable: bool | None
		:return:
	"""
	if enable is True or enable is False or enable is None:
		conf["viur.security.xXssProtection"] = enable
	else:
		raise ValueError("enable must be exactly one of None | True | False")


def setXContentTypeNoSniff(enable):
	"""
		Sets X-Content-Type-Options if enable is true, otherwise no header is emited.
		:param enable: Enable emitting this header or not
		:type enable: bool
		:return:
	"""
	if enable is True or enable is False:
		conf["viur.security.xContentTypeOptions"] = enable
	else:
		raise ValueError("enable must be one of True | False")


def setXPermittedCrossDomainPolicies(value):
	if value not in [None, "none", "master-only", "by-content-type", "all"]:
		raise ValueError("value [None, \"none\", \"master-only\", \"by-content-type\", \"all\"]")
	conf["viur.security.xPermittedCrossDomainPolicies"] = value
