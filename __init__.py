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

__version__ = (2, 5, 0)  # Which API do we expose to our application

import sys, traceback, os, inspect

## All (optional) 3rd-party modules in our libs-directory
# cwd = os.path.abspath(os.path.dirname(__file__))
#
# for lib in os.listdir(os.path.join(cwd, "libs")):
#	if not lib.lower().endswith(".zip"):  # Skip invalid file
#		continue
#	sys.path.insert(0, os.path.join(cwd, "libs", lib))

from server.config import conf, sharedConf
from server import request
import server.languages as servertrans
# from google.appengine.ext import webapp
# from google.appengine.ext.webapp.util import run_wsgi_app
# from google.appengine.api import users
# import urlparse

from string import Template
# from StringIO import StringIO
import logging
from time import time
import webob

# Copy our Version into the config so that our renders can access it
conf["viur.version"] = __version__

### Multi-Language Part
try:
	import translations

	conf["viur.availableLanguages"].extend([x for x in dir(translations) if (len(x) == 2 and not x.startswith("_"))])
except ImportError:  # The Project doesnt use Multi-Language features
	translations = None


def translate(key, **kwargs):
	"""
	Translate *key* into language text pendant.

	This function is part of ViURs language support facilities for supporting internationalization (i18n).

	Translations are provided in the applications *translations* module in form of a dict, where the keys
	should be the language strings in the project's major language (usually english), and the values the
	strings provided in the particular language implemented. The translation key strings must be given
	in a lower-case order, altought they may be capitalized or upper-case written. If no key is found
	within a specific translation, it is directly used as the output string.

	The strings may contain placeholders in form ``{{placeholer}}``, which can be assigned via the
	*kwargs* argument.

	``translate()`` is also provided as ``_()`` as global function.

	In this simple example, a file ``translations/de.py`` is implemented with the content:

	.. code-block:: python

		de = {
				"welcome to viur": u"Willkommen in ViUR",
				"hello {{user}}!": u"Hallo, {{user}}!"
		}

	To support internationalization, it is simply done this way:

	.. code-block:: python

		txt = _( "Hello {{user}}!", user="John Doe" ) + " - "  + _( "Welcome to ViUR" )

	Language support is also provided in Jinja2-templates like this:

	.. code-block:: jinja

		{{ _( "Hello {{user}}!", user="John Doe" ) }} - {{ _( "Welcome to ViUR" ) }}

	This will both output "Hello John Doe! - Welcome to ViUR" in an english-configured language environment,
	and "Hallo John Doe! - Willkommen in ViUR" in a german-configured language environment.

	The current session language (or default language) can be overridden with ``_lang``, e.g.

	.. code-block:: python

		txt = _( "Hello {{user}}!", user="John Doe" ) + " - "  + _( "Welcome to ViUR", lang="en" )

	will result in "Hallo John Doe! - Welcome to ViUR" in a german-configured language environment.

	:param key: The key value that should be translated; If no key is found in the configured language,
		key is directly used.
	:type key: str
	:param kwargs: May contain place-holders replaced as ``{{placeholer}}`` within the key or translation.
		The special-value ``_lang`` overrides the current language setting.

	:return: Translated text or key, with replaced placeholders, if given.
	:rtype: str
	"""

	try:
		lang = request.current.get().language
	except:
		return (key)

	if key is None:
		return (None)
	elif not isinstance(key, basestring):
		raise ValueError("Can only translate strings, got %s instead" % str(type(key)))

	res = None
	lang = lang or conf["viur.defaultLanguage"]

	if "_lang" in kwargs:
		lang = kwargs["_lang"]

	if lang in conf["viur.languageAliasMap"]:
		lang = conf["viur.languageAliasMap"][lang]

	if lang and lang in dir(translations):
		langDict = getattr(translations, lang)

		if key.lower() in langDict:
			res = langDict[key.lower()]

	if res is None and lang and lang in dir(servertrans):
		langDict = getattr(servertrans, lang)

		if key.lower() in langDict:
			res = langDict[key.lower()]

	if res is None and conf["viur.logMissingTranslations"]:
		from server import db
		db.GetOrInsert(key="%s-%s" % (key, str(lang)),
					   kindName="viur-missing-translations",
					   langkey=key, lang=lang)

	if res is None:
		res = key

	for k, v in kwargs.items():
		res = res.replace("{{%s}}" % k, str(v))

	return (res)


__builtins__["_"] = translate  # Install the global "_"-Function


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

from server import session, errors
from server.tasks import TaskHandler, runStartupTasks


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
	else:  # build up the dict from server.render
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

	for moduleName in dir(config):  # iterate over all modules
		if moduleName == "index":
			continue

		for renderName in list(rendlist.keys()):  # look, if a particular render should be built
			if renderName in dir(getattr(config, moduleName)) \
					and getattr(getattr(config, moduleName), renderName) == True:
				modulePath = "%s/%s" % ("/" + renderName if renderName != default else "", moduleName)
				obj = getattr(config, moduleName)(moduleName, modulePath)
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

	if not isinstance(renderers, dict):  # Apply Renderers postProcess Filters
		for renderName in list(rendlist.keys()):
			rend = getattr(renderers, renderName)
			if "_postProcessAppObj" in dir(rend):
				if renderName == default:
					res = rend._postProcessAppObj(res)
				else:
					if (renderName in dir(res)):
						setattr(res, renderName, rend._postProcessAppObj(getattr(res, renderName)))
	else:
		for renderName in list(rendlist.keys()):
			rend = rendlist[renderName]
			if "_postProcessAppObj" in list(rend.keys()):
				if renderName == default:
					res = rend["_postProcessAppObj"](res)
				else:
					if renderName in dir(res):
						setattr(res, renderName, rend["_postProcessAppObj"](getattr(res, renderName)))

	if conf["viur.exportPassword"] is not None or conf["viur.importPassword"] is not None:
		# Enable the Database ex/import API
		from server.dbtransfer import DbTransfer
		if conf["viur.importPassword"]:
			logging.critical("The Import-API is enabled! Never do this on production systems!")
			from server import utils
			try:
				utils.sendEMailToAdmins("Active Database import API",
										"ViUR just started a new Instance with an ENABLED DATABASE IMPORT API! You have been warned.")
			except:  # OverQuota, whatever
				pass  # Dont render this instance unusable
		elif conf["viur.exportPassword"]:
			logging.warning("The Export-API is enabled. Everyone having that key can read the whole database!")

		setattr(res, "dbtransfer", DbTransfer())
	if conf["viur.debug.traceExternalCallRouting"] or conf["viur.debug.traceInternalCallRouting"]:
		from server import utils
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

	from server.bones import bone

	if not render:
		import server.render
		render = server.render
	conf["viur.mainApp"] = buildApp(modules, render, default)
	renderPrefix = ["/%s" % x for x in dir(render) if (not x.startswith("_") and x != default)] + [""]
	# conf["viur.wsgiApp"] = webapp.WSGIApplication([(r'/(.*)', BrowseHandler)])
	# Ensure that our Content Security Policy Header Cache gets build
	from server import securityheaders
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
	return app
	return (conf["viur.wsgiApp"])


def run():
	"""
		Runs the previously configured server.
	"""


# run_wsgi_app(conf["viur.wsgiApp"])

def app(environ, start_response):
	req = webob.Request(environ)
	resp = webob.Response()
	handler = request.BrowseHandler(req, resp)
	request.current.setRequest(handler)
	handler.processRequest()
	request.current.setRequest(None)
	return resp(environ, start_response)


## Decorators ##
def forceSSL(f):
	"""
		Decorator, which forces usage of an encrypted Cchannel for a given resource.
		Has no effects on development-servers.
	"""
	f.forceSSL = True
	return (f)


def forcePost(f):
	"""
		Decorator, which forces usage of an http post request.
	"""
	f.forcePost = True
	return (f)


def exposed(f):
	"""
		Decorator, which marks an function as exposed.

		Only exposed functions are callable by http-requests.
	"""
	f.exposed = True
	return (f)


def internalExposed(f):
	"""
		Decorator, marks an function as internal exposed.

		Internal exposed functions are not callable by external http-requests,
		but can be called by templates using ``execRequest()``.
	"""
	f.internalExposed = True
	return (f)
