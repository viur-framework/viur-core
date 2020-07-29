# -*- coding: utf-8 -*-
"""
                 iii
                iii
               iii

           vvv iii uu      uu rrrrrrrr
          vvvv iii uu      uu rr     rr
  v      vvvv  iii uu      uu rr     rr
  vv    vvvv   iii uu      uu rr rrrrr
 vvvv  vvvv    iii uu      uu rr rrr
  vvv vvvv     iii uu      uu rr  rrr
   vvvvvv      iii  uu    uu  rr   rrr
    vvvv       iii   uuuuuu   rr    rrr

   I N F O R M A T I O N    S Y S T E M

 ViUR SERVER
 Copyright 2012-2019 by Mausbrand Informationssysteme GmbH

 ViUR is a free software development framework for the Google App Engine™.
 More about ViUR can be found at https://www.viur.is/.

 Licensed under the GNU Lesser General Public License, version 3.
 See file LICENSE for more information.
"""

__version__ = (3, -99, -99)  # Which API do we expose to our application



from viur.core.config import conf
from viur.core import request
from viur.core import languages as servertrans
from viur.core.i18n import initializeTranslations
from viur.core import logging as viurLogging  # Initialize request logging
from viur.core.utils import currentRequest, currentSession, currentLanguage, currentRequestData
from viur.core.session import GaeSession
import logging
import webob

# Copy our Version into the config so that our renders can access it
conf["viur.version"] = __version__



def setDefaultLanguage(lang):
	"""
	Configures default language to *lang*.

	:param lang: Name of the language module to use by default.
	:type lang: str
	"""
	conf["viur.defaultLanguage"] = lang.lower()


def setDefaultDomainLanguage(domain, lang):
	host = domain.lower().strip(" /")
	if host.startswith("www."):
		host = host[4:]
	conf["viur.domainLanguageMapping"][host] = lang.lower()


### Multi-Language Part: END

from viur.core import session, errors
from viur.core.tasks import TaskHandler, runStartupTasks
from viur.core import i18n


def mapModule(moduleObj: object, moduleName: str, targetResoveRender: dict):
	"""
		Maps each function that's exposed of moduleObj into the branch of `prop:server.conf["viur.mainResolver"]`
		that's referenced by `prop:targetResoveRender`. Will also walk `prop:_viurMapSubmodules` if set
		and map these sub-modules also.
	"""
	moduleFunctions = {}
	for key in [x for x in dir(moduleObj) if x[0] != "_"]:
		prop = getattr(moduleObj, key)
		if key == "canAccess" or getattr(prop, "exposed", None):
			moduleFunctions[key] = prop
	for lang in conf["viur.availableLanguages"] or [conf["viur.defaultLanguage"]]:
		# Map the module under each translation
		if "seoLanguageMap" in dir(moduleObj) and lang in moduleObj.seoLanguageMap:
			translatedModuleName = moduleObj.seoLanguageMap[lang]
			if not translatedModuleName in targetResoveRender:
				targetResoveRender[translatedModuleName] = {}
			for fname, fcall in moduleFunctions.items():
				targetResoveRender[translatedModuleName][fname] = fcall
				# Map translated function names
				if getattr(fcall, "seoLanguageMap", None) and lang in fcall.seoLanguageMap:
					targetResoveRender[translatedModuleName][fcall.seoLanguageMap[lang]] = fcall
			if "_viurMapSubmodules" in dir(moduleObj):
				# Map any Functions on deeper nested function
				subModules = moduleObj._viurMapSubmodules
				for subModule in subModules:
					obj = getattr(moduleObj, subModule, None)
					if obj:
						mapModule(obj, subModule, targetResoveRender[translatedModuleName])
	if moduleName == "index":
		targetFunctionLevel = targetResoveRender
	else:
		# Map the module also under it's original name
		if not moduleName in targetResoveRender:
			targetResoveRender[moduleName] = {}
		targetFunctionLevel = targetResoveRender[moduleName]
	for fname, fcall in moduleFunctions.items():
		targetFunctionLevel[fname] = fcall
		# Map translated function names
		if getattr(fcall, "seoLanguageMap", None):
			for translatedFunctionName in fcall.seoLanguageMap.values():
				targetFunctionLevel[translatedFunctionName] = fcall
	if "_viurMapSubmodules" in dir(moduleObj):
		# Map any Functions on deeper nested function
		subModules = moduleObj._viurMapSubmodules
		for subModule in subModules:
			obj = getattr(moduleObj, subModule, None)
			if obj:
				mapModule(obj, subModule, targetFunctionLevel)


def buildApp(config, renderers, default=None, *args, **kwargs):
	"""
		Creates the application-context for the current instance.

		This function converts the classes found in the *modules*-module,
		and the given renders into the object found at ``conf["viur.mainApp"]``.

		Every class found in *modules* becomes

		- instanced
		- get the corresponding renderer attached
		- will be attached to ``conf["viur.mainApp"]``

		:param config: Usually the module provided as *modules* directory within the application.
		:type config: module | object
		:param renders: Usually the module *server.renders*, or a dictionary renderName => renderClass.
		:type renders: module | dict
		:param default: Name of the renderer, which will form the root of the application.\
		This will be the renderer, which wont get a prefix, usually jinja2. \
		(=> /user instead of /jinja2/user)
		:type default: str
	"""

	class ExtendableObject(object):
		pass

	if isinstance(renderers, dict):
		rendlist = renderers
	else:  # build up the dict from viur.core.render
		rendlist = {}
		for key in dir(renderers):
			if not "__" in key:
				rendlist[key] = {}
				rendsublist = getattr(renderers, key)
				for subkey in dir(rendsublist):
					if not "__" in subkey:
						rendlist[key][subkey] = getattr(rendsublist, subkey)
	if "index" in dir(config):
		res = config.index()
	else:
		res = ExtendableObject()
	config._tasks = TaskHandler
	resolverDict = {}
	for moduleName in dir(config):  # iterate over all modules
		if moduleName == "index":
			mapModule(res, "index", resolverDict)
			continue
		moduleClass = getattr(config, moduleName)
		for renderName in list(rendlist.keys()):  # look, if a particular render should be built
			if renderName in dir(getattr(config, moduleName)) \
					and getattr(getattr(config, moduleName), renderName) == True:
				modulePath = "%s/%s" % ("/" + renderName if renderName != default else "", moduleName)
				obj = moduleClass(moduleName, modulePath)
				if moduleName in rendlist[renderName]:  # we have a special render for this
					obj.render = rendlist[renderName][moduleName](parent=obj)
				else:  # Attach the default render
					obj.render = rendlist[renderName]["default"](parent=obj)
				setattr(obj, "_moduleName", moduleName)
				if renderName == default:  # default or render (sub)namespace?
					setattr(res, moduleName, obj)
				else:
					if not renderName in dir(res):
						setattr(res, renderName, ExtendableObject())
					setattr(getattr(res, renderName), moduleName, obj)
				if renderName != default:
					if not renderName in resolverDict:
						resolverDict[renderName] = {}
					targetResoveRender = resolverDict[renderName]
				else:
					targetResoveRender = resolverDict
				mapModule(obj, moduleName, targetResoveRender)
				# Apply Renderers postProcess Filters
				if "_postProcessAppObj" in rendlist[renderName]:
					rendlist[renderName]["_postProcessAppObj"](targetResoveRender)
		if "seoLanguageMap" in dir(moduleClass):
			conf["viur.languageModuleMap"][moduleName] = moduleClass.seoLanguageMap
	conf["viur.mainResolver"] = resolverDict
	if conf["viur.exportPassword"] is not None or conf["viur.importPassword"] is not None:
		# Enable the Database ex/import API
		from viur.core.dbtransfer import DbTransfer
		if conf["viur.importPassword"]:
			logging.critical("The Import-API is enabled! Never do this on production systems!")
			from viur.core import utils
			try:
				utils.sendEMailToAdmins("Active Database import API",
										"ViUR just started a new Instance with an ENABLED DATABASE IMPORT API! You have been warned.")
			except:  # OverQuota, whatever
				pass  # Dont render this instance unusable
		elif conf["viur.exportPassword"]:
			logging.warning("The Export-API is enabled. Everyone having that key can read the whole database!")

		setattr(res, "dbtransfer", DbTransfer())
		mapModule(res.dbtransfer, "dbtransfer", resolverDict)
		#resolverDict["dbtransfer"]
	if conf["viur.debug.traceExternalCallRouting"] or conf["viur.debug.traceInternalCallRouting"]:
		from viur.core import utils
		try:
			utils.sendEMailToAdmins("Debug mode enabled",
									"ViUR just started a new Instance with calltracing enabled! This will log sensitive information!")
		except:  # OverQuota, whatever
			pass  # Dont render this instance unusable
	if default in rendlist and "renderEmail" in dir(rendlist[default]["default"]()):
		conf["viur.emailRenderer"] = rendlist[default]["default"]().renderEmail
	elif "html" in list(rendlist.keys()):
		conf["viur.emailRenderer"] = rendlist["html"]["default"]().renderEmail

	return res


def setup(modules, render=None, default="html"):
	"""
		Define whats going to be served by this instance.

		:param config: Usually the module provided as *modules* directory within the application.
		:type config: module | object
		:param renders: Usually the module *server.renders*, or a dictionary renderName => renderClass.
		:type renders: module | dict
		:param default: Name of the renderer, which will form the root of the application.\
		This will be the renderer, which wont get a prefix, usually html. \
		(=> /user instead of /html/user)
		:type default: str
	"""
	import skeletons  # This import is not used here but _must_ remain to ensure that the
	# application's data models are explicitly imported at some place!

	from viur.core.bones import bone

	if not render:
		import viur.core.render
		render = viur.core.render
	conf["viur.mainApp"] = buildApp(modules, render, default)
	renderPrefix = ["/%s" % x for x in dir(render) if (not x.startswith("_") and x != default)] + [""]
	# conf["viur.wsgiApp"] = webapp.WSGIApplication([(r'/(.*)', BrowseHandler)])
	# Ensure that our Content Security Policy Header Cache gets build
	from viur.core import securityheaders
	securityheaders._rebuildCspHeaderCache()
	bone.setSystemInitialized()
	# Assert that all security releated headers are in a sane state
	if conf["viur.security.contentSecurityPolicy"] and conf["viur.security.contentSecurityPolicy"]["_headerCache"]:
		for k, v in conf["viur.security.contentSecurityPolicy"]["_headerCache"].items():
			assert k.startswith(
				"Content-Security-Policy"), "Got unexpected header in conf['viur.security.contentSecurityPolicy']['_headerCache']"
	if conf["viur.security.strictTransportSecurity"]:
		assert conf["viur.security.strictTransportSecurity"].startswith(
			"max-age"), "Got unexpected header in conf['viur.security.strictTransportSecurity']"
	if conf["viur.security.publicKeyPins"]:
		assert conf["viur.security.publicKeyPins"].startswith(
			"pin-"), "Got unexpected header in conf['viur.security.publicKeyPins']"
	assert conf["viur.security.xPermittedCrossDomainPolicies"] in [None, "none", "master-only", "by-content-type",
																   "all"], \
		"conf[\"viur.security.xPermittedCrossDomainPolicies\"] must be one of [None, \"none\", \"master-only\", \"by-content-type\", \"all\"]"
	if conf["viur.security.xFrameOptions"] is not None and isinstance(conf["viur.security.xFrameOptions"], tuple):
		mode, uri = conf["viur.security.xFrameOptions"]
		assert mode in ["deny", "sameorigin", "allow-from"]
		if mode == "allow-from":
			assert uri is not None and (
					uri.lower().startswith("https://") or uri.lower().startswith("http://"))
	runStartupTasks()  # Add a deferred call to run all queued startup tasks
	initializeTranslations()
	assert conf["viur.file.hmacKey"], "You must set a secret and unique Application-Key to viur.file.hmacKey"
	return app



def app(environ, start_response):
	req = webob.Request(environ)
	resp = webob.Response()
	handler = request.BrowseHandler(req, resp)
	currentRequest.set(handler)
	currentSession.set(GaeSession())
	currentRequestData.set({})
	handler.processRequest()
	currentRequestData.set(None)
	currentSession.set(None)
	currentRequest.set(None)
	return resp(environ, start_response)


## Decorators ##
def forceSSL(f):
	"""
		Decorator, which forces usage of an encrypted Channel for a given resource.
		Has no effect on development-servers.
	"""
	f.forceSSL = True
	return f


def forcePost(f):
	"""
		Decorator, which forces usage of an http post request.
	"""
	f.forcePost = True
	return f


def exposed(f):
	"""
		Decorator, which marks an function as exposed.

		Only exposed functions are callable by http-requests.
		Can optionally receive a dict of language->translated name to make that function
		available under different names
	"""
	if isinstance(f, dict):
		# We received said dictionary:
		def exposeWithTranslations(g):
			g.exposed = True
			g.seoLanguageMap = f
			return g
		return exposeWithTranslations
	else:
		f.exposed = True
		f.seoLanguageMap = None
		return f


def internalExposed(f):
	"""
		Decorator, marks an function as internal exposed.

		Internal exposed functions are not callable by external http-requests,
		but can be called by templates using ``execRequest()``.
	"""
	f.internalExposed = True
	return f
