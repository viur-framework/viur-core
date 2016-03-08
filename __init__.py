#-*- coding: utf-8 -*-
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
 Copyright 2012-2016 by mausbrand Informationssysteme GmbH

 http://www.viur.is

 Licensed under the GNU Lesser General Public License, version 3.
 See file LICENSE for more information.
"""

__version__ = (-99,-99,-99) #Which API do we expose to our application

import sys, traceback, os, inspect

#All (optional) 3rd-party modules in our libs-directory
cwd = os.path.abspath(os.path.dirname(__file__))

for lib in os.listdir( os.path.join(cwd, "libs") ):
	if not lib.lower().endswith(".zip"): #Skip invalid file
		continue
	sys.path.insert(0, os.path.join( cwd, "libs", lib ) )

from server.config import conf, sharedConf
from server import request
import server.languages as servertrans
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import users
import urlparse

from string import Template
from StringIO import StringIO
import logging

### Multi-Language Part
try:
	import translations
	conf["viur.availableLanguages"].extend( [x for x in dir( translations ) if (len(x)==2 and not x.startswith("_")) ] )
except ImportError: #The Project doesnt use Multi-Language features
	translations = None

def translate( key, **kwargs ):
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

	.. code-block:: jinja2
		{{ _( "Hello {{user}}!", user="John Doe" ) }} - {{ _( "Welcome to ViUR" ) }}

	This will both output "Hello John Doe! - Welcome to ViUR" in an english-configured language environment,
	and "Hallo John Doe! - Willkommen in ViUR" in a german-configured language environment.

	The current session language (or default language) can be overridden with ``_lang``, e.g.

	.. code-block:: python
		txt = _( "Hello {{user}}!", user="John Doe" ) + " - "  + _( "Welcome to ViUR", lang="en" )

	will result in "Hallo John Doe! - Welcome to ViUR" in a german-configured language environment.

	:param key: The key value that should be translated; If no key is found in the configured language,\
	key is directly used.
	:type key: str
	:param kwargs: May contain place-holders replaced as ``{{placeholer}}`` within the key or translation.\
	The special-value ``_lang`` overrides the current language setting.

	:return: Translated text or key, with replaced placeholders, if given.
	:rtype: str
	"""

	try:
		lang = request.current.get().language
	except:
		return( key )

	if key is None:
		return( None )
	elif not isinstance( key, basestring ):
		raise ValueError("Can only translate strings, got %s instead" % str(type(key)))

	res = None
	lang = lang or conf["viur.defaultLanguage"]

	if "_lang" in kwargs.keys():
		lang = kwargs[ "_lang" ]

	if lang in conf["viur.languageAliasMap"].keys():
		lang = conf["viur.languageAliasMap"][ lang ]

	if lang and lang in dir( translations ):
		langDict = getattr(translations,lang)

		if key.lower() in langDict.keys():
			res = langDict[ key.lower() ]

	if res is None and lang and lang in dir( servertrans ):
		langDict = getattr(servertrans,lang)

		if key.lower() in langDict.keys():
			res = langDict[ key.lower() ]

	if res is None and conf["viur.logMissingTranslations"]:
		from server import db
		db.GetOrInsert( key="%s-%s" % ( key, str( lang )),
		                kindName="viur-missing-translations",
		                langkey=key, lang=lang )

	if res is None:
		res = key

	for k, v in kwargs.items():
		res = res.replace("{{%s}}"%k, unicode(v) )

	return( res )

__builtins__["_"] = translate #Install the global "_"-Function


def setDefaultLanguage( lang ):
	"""
	Configures default language to *lang*.

	:param lang: Name of the language module to use by default.
	:type lang: str
	"""
	conf["viur.defaultLanguage"] = lang.lower()

def setDefaultDomainLanguage( domain, lang ):
	host = domain.lower().strip(" /")
	if host.startswith("www."):
		host = host[ 4: ]
	conf["viur.domainLanguageMapping"][host] = lang.lower()

### Multi-Language Part: END 

from server import session, errors
from server.tasks import TaskHandler, runStartupTasks

try:
	import bugsnag
	from google.appengine.api import app_identity
	try:
		appVersion = app_identity.get_default_version_hostname()
		if ".appspot.com" in appVersion.lower():
			appVersion = appVersion.replace(".appspot.com", "")
			releaseStage = "production"
		else:
			appVersion = "-unknown-"
			releaseStage = "development"
	except:
		appVersion = "-error-"
		releaseStage = "production"
	bugsnag.configure(	use_ssl=True,
				release_stage = releaseStage,
				auto_notify = False,
				app_version=appVersion,
				notify_release_stages = ["production"]
				)
except:
	bugsnag = None

def buildApp( config, renderers, default=None, *args, **kwargs ):
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
	class ExtendableObject( object ):
		pass
		
	if isinstance( renderers,  dict ):
		rendlist = renderers
	else: # build up the dict from server.render
		rendlist = {}
		for key in dir( renderers ):
			if not "__" in key:
				rendlist[ key ] = {}
				rendsublist = getattr( renderers,  key )
				for subkey in dir(  rendsublist ):
					if not "__" in subkey:
						rendlist[ key ][ subkey ] = getattr( rendsublist,  subkey )

	if "index" in dir( config ):
		res = config.index()
	else:
		res = ExtendableObject()

	config._tasks = TaskHandler

	for moduleName in dir( config ): # iterate over all modules
		if moduleName=="index":
			continue

		for renderName in list(rendlist.keys()): # look, if a particular render should be built
			if renderName in dir( getattr( config, moduleName ) ) \
				and getattr( getattr( config, moduleName ) , renderName )==True:
					modulePath = "%s/%s" % ("/"+renderName if renderName!=default else "",  moduleName)
					obj =  getattr( config,  moduleName)( moduleName, modulePath )
					if moduleName in rendlist[ renderName ]: # we have a special render for this
						obj.render = rendlist[ renderName ][ moduleName ]( parent = obj )
					else: # Attach the default render
						obj.render = rendlist[ renderName ][ "default" ]( parent = obj )
					setattr(obj,"_moduleName",moduleName)
					if renderName == default: #default or render (sub)namespace?
						setattr( res,  moduleName, obj )
					else:
						if not renderName in dir( res ):
							setattr( res,  renderName,  ExtendableObject() )
						setattr( getattr(res, renderName), moduleName, obj )

	if not isinstance( renderers, dict ): # Apply Renderers postProcess Filters
		for renderName in list(rendlist.keys()):
			rend = getattr( renderers, renderName )
			if "_postProcessAppObj" in dir( rend ):
				if renderName==default:
					res = rend._postProcessAppObj( res )
				else:
					if( renderName in dir( res )):
						setattr( res, renderName,  rend._postProcessAppObj( getattr( res,renderName ) ) )
	else:
		for renderName in list(rendlist.keys()):
			rend = rendlist[renderName]
			if "_postProcessAppObj" in list(rend.keys()):
				if renderName==default:
					res = rend["_postProcessAppObj"]( res )
				else:
					if renderName in dir(res):
						setattr( res, renderName,  rend["_postProcessAppObj"]( getattr( res,renderName ) ) )

	if conf["viur.exportPassword"] is not None or conf["viur.importPassword"] is not None:
		# Enable the Database ex/import API
		from server.dbtransfer import DbTransfer
		if conf["viur.importPassword"]:
			logging.critical("The Import-API is enabled! Never do this on production systems!")
			from server import utils
			try:
				utils.sendEMailToAdmins("Active Database import API",
							"ViUR just started a new Instance with an ENABLED DATABASE IMPORT API! You have been warned.")
			except: #OverQuota, whatever
				pass #Dont render this instance unusable
		elif conf["viur.exportPassword"]:
			logging.warning("The Export-API is enabled. Everyone having that key can read the whole database!")

		setattr( res, "dbtransfer", DbTransfer() )

	if default in rendlist and "renderEmail" in dir (rendlist[ default ]["default"]()):
		conf["viur.emailRenderer"] = rendlist[ default ]["default"]().renderEmail
	elif "jinja2" in list(rendlist.keys()):
		conf["viur.emailRenderer"] = rendlist[ "jinja2" ]["default"]().renderEmail

	return res

class BrowseHandler(webapp.RequestHandler):
	"""
		This class accepts the requests, collect its parameters and routes the request
		to its destination function.

		:warning: Don't instantiate! Don't subclass! DON'T TOUCH! ;)
	"""
	
	def get(self, path="/", *args, **kwargs): #Accept a HTTP-GET request
		if path=="_ah/start" or path=="_ah/warmup": #Warmup request
			self.response.out.write("OK")
			return

		self.isPostRequest = False
		self.processRequest( path, *args, **kwargs )

	def post(self, path="/", *args, **kwargs): #Accept a HTTP-POST request
		self.isPostRequest = True
		self.processRequest( path, *args, **kwargs )

	def head(self, path="/", *args, **kwargs): #Accept a HTTP-HEAD request
		self.isPostRequest = False
		self.processRequest( path, *args, **kwargs )
		
	def selectLanguage( self, path ):
		"""
			Tries to select the best language for the current request.
		"""
		if translations is None:
			# This project doesn't use the multi-language feature, nothing to do here
			return( path )
		if conf["viur.languageMethod"] == "session":
			# We store the language inside the session, try to load it from there
			if not session.current.getLanguage():
				if "X-Appengine-Country" in self.request.headers.keys():
					lng = self.request.headers["X-Appengine-Country"].lower()
					if lng in conf["viur.availableLanguages"]+list( conf["viur.languageAliasMap"].keys() ):
						session.current.setLanguage( lng )
						self.language = lng
					else:
						session.current.setLanguage( conf["viur.defaultLanguage"] )
			else:
				self.language = session.current.getLanguage()
		elif conf["viur.languageMethod"] == "domain":
			host = self.request.host_url.lower()
			host = host[ host.find("://")+3: ].strip(" /") #strip http(s)://
			if host.startswith("www."):
				host = host[ 4: ]
			if host in conf["viur.domainLanguageMapping"].keys():
				self.language = conf["viur.domainLanguageMapping"][ host ]
			else: # We have no language configured for this domain, try to read it from session
				if session.current.getLanguage():
					self.language = session.current.getLanguage()
		elif conf["viur.languageMethod"] == "url":
			tmppath = urlparse.urlparse( path ).path
			tmppath = [ urlparse.unquote( x ) for x in tmppath.lower().strip("/").split("/") ]
			if len( tmppath )>0 and tmppath[0] in conf["viur.availableLanguages"]+list( conf["viur.languageAliasMap"].keys() ):
				self.language = tmppath[0]
				return( path[ len( tmppath[0])+1: ] ) #Return the path stripped by its language segment
			else: # This URL doesnt contain an language prefix, try to read it from session
				if session.current.getLanguage():
					self.language = session.current.getLanguage()
		return( path )


	def processRequest( self, path, *args, **kwargs ): #Bring up the enviroment for this request, handle errors
		self.internalRequest = False
		self.isDevServer = "Development" in os.environ['SERVER_SOFTWARE'] #Were running on development Server
		self.isSSLConnection = self.request.host_url.lower().startswith("https://") #We have an encrypted channel
		self.language = conf["viur.defaultLanguage"]
		self.disableCache = False # Shall this request bypass the caches?
		request.current.setRequest( self )
		self.args = []
		self.kwargs = {}
		#Add CSP headers early (if any)
		if conf["viur.security.contentSecurityPolicy"] and conf["viur.security.contentSecurityPolicy"]["_headerCache"]:
			for k,v in conf["viur.security.contentSecurityPolicy"]["_headerCache"].items():
				assert k.startswith("Content-Security-Policy"), "Got unexpected header in conf['viur.security.contentSecurityPolicy']['_headerCache']"
				self.response.headers[k] = v
		if self.isSSLConnection: #Check for HTST and PKP headers only if we have a secure channel.
			if conf["viur.security.strictTransportSecurity"]:
				assert conf["viur.security.strictTransportSecurity"].startswith("max-age"), "Got unexpected header in conf['viur.security.strictTransportSecurity']"
				self.response.headers["Strict-Transport-Security"] = conf["viur.security.strictTransportSecurity"]
			if conf["viur.security.publicKeyPins"]:
				assert conf["viur.security.publicKeyPins"].startswith("pin-"), "Got unexpected header in conf['viur.security.publicKeyPins']"
				self.response.headers["Public-Key-Pins"] = conf["viur.security.publicKeyPins"]
		# Check for X-Security-Headers we shall emit
		if conf["viur.security.xContentTypeOptions"]:
			self.response.headers["X-Content-Type-Options"] = "nosniff"
		if conf["viur.security.xXssProtection"] is not None:
			if conf["viur.security.xXssProtection"]:
				self.response.headers["X-XSS-Protection"] = "1; mode=block"
			elif conf["viur.security.xXssProtection"] is False:
				self.response.headers["X-XSS-Protection"] = "0"
		if conf["viur.security.xFrameOptions"] is not None and isinstance(conf["viur.security.xFrameOptions"], tuple):
			mode, uri = conf["viur.security.xFrameOptions"]
			assert mode in ["deny", "sameorigin","allow-from"]
			if mode in ["deny", "sameorigin"]:
				self.response.headers["X-Frame-Options"] = mode
			elif mode=="allow-from":
				assert uri is not None and (uri.lower().startswith("https://") or uri.lower().startswith("http://"))
				self.response.headers["X-Frame-Options"] = "allow-from %s" % uri
		if sharedConf["viur.disabled"] and not (users.is_current_user_admin() or "HTTP_X_QUEUE_NAME".lower() in [x.lower() for x in os.environ.keys()] ): #FIXME: Validate this works
			self.response.set_status( 503 ) #Service unavailable
			tpl = Template( open("server/template/error.html", "r").read() )
			if isinstance( sharedConf["viur.disabled"], basestring ):
				msg = sharedConf["viur.disabled"]
			else:
				msg = "This application is currently disabled or performing maintenance. Try again later."
			self.response.out.write( tpl.safe_substitute( {"error_code": "503", "error_name": "Service unavailable", "error_descr": msg} ) )
			return
		if conf["viur.forceSSL"] and not self.isSSLConnection and not self.isDevServer:
			isWhitelisted = False
			reqPath = self.request.path
			for testUrl in conf["viur.noSSLCheckUrls"]:
				if testUrl.endswith("*"):
					if reqPath.startswith(testUrl[:-1]):
						isWhitelisted = True
						break
				else:
					if testUrl==reqPath:
						isWhitelisted = True
						break
			if not isWhitelisted: # Some URLs need to be whitelisted (as f.e. the Tasks-Queue doesn't call using https)
				#Redirect the user to the startpage (using ssl this time)
				host = self.request.host_url.lower()
				host = host[ host.find("://")+3: ].strip(" /") #strip http(s)://
				self.redirect( "https://%s/" % host )
				return
		try:
			session.current.load( self ) # self.request.cookies )
			path = self.selectLanguage( path )
			if conf["viur.requestPreprocessor"]:
				path = conf["viur.requestPreprocessor"]( path )
			self.findAndCall( path, *args, **kwargs )
		except errors.Redirect as e :
			if conf["viur.debug.traceExceptions"]:
				raise
			self.redirect( e.url.encode("UTF-8") )
		except errors.HTTPException as e:
			if conf["viur.debug.traceExceptions"]:
				raise
			self.response.clear()
			self.response.set_status( e.status )
			res = None
			if conf["viur.errorHandler"]:
				try:
					res = conf["viur.errorHandler"]( e )
				except Exception as newE:
					logging.error("viur.errorHandler failed!")
					logging.exception( newE )
					res = None
			if not res:
				tpl = Template( open(conf["viur.errorTemplate"], "r").read() )
				res = tpl.safe_substitute( {"error_code": e.status, "error_name":e.name, "error_descr": e.descr} )
			self.response.out.write( res )
		except Exception as e: #Something got really wrong
			logging.exception( "Viur caught an unhandled exception!" )
			self.response.clear()
			self.response.set_status( 500 )
			res = None
			if conf["viur.errorHandler"]:
				try:
					res = conf["viur.errorHandler"]( e )
				except Exception as newE:
					logging.error("viur.errorHandler failed!")
					logging.exception( newE )
					res = None
			if not res:
				tpl = Template( open(conf["viur.errorTemplate"], "r").read() )
				descr = "The server encountered an unexpected error and is unable to process your request."
				if self.isDevServer: #Were running on development Server
					strIO = StringIO()
					traceback.print_exc(file=strIO)
					descr= strIO.getvalue()
					descr = descr.replace("<","&lt;").replace(">","&gt;").replace(" ", "&nbsp;").replace("\n", "<br />")
				res = tpl.safe_substitute( {"error_code": "500", "error_name":"Internal Server Error", "error_descr": descr} )
			self.response.out.write( res )
			if bugsnag and conf["bugsnag.apiKey" ]:
				bugsnag.configure( api_key=conf["bugsnag.apiKey" ] )
				try: 
					user = conf["viur.mainApp"].user.getCurrentUser()
				except:
					user = "-unknown-"
				try:
					sessData = session.current.session.session
				except:
					sessData = None
				bugsnag.configure_request( context=path, user_id=user, session_data=sessData )
				bugsnag.notify( e )
		finally:
			self.saveSession( )
	

	def findAndCall( self, path, *args, **kwargs ): #Do the actual work: process the request
		# Prevent Hash-collision attacks
		assert len( self.request.arguments() ) < conf["viur.maxPostParamsCount"]
		# Fill the (surprisingly empty) kwargs dict with named request params
		tmpArgs = dict( (k,self.request.get_all(k)) for k in self.request.arguments() )
		for key in tmpArgs.keys()[ : ]:
			if len( tmpArgs[ key ] ) == 0:
				continue
			if not key in kwargs.keys():
				if len( tmpArgs[ key ] ) == 1:
					kwargs[ key ] = tmpArgs[ key ][0]
				else:
					kwargs[ key ] = tmpArgs[ key ]
			else:
				if isinstance( kwargs[key], list ):
					kwargs[key] = kwargs[key] + tmpArgs[key]
				else:
					kwargs[key] = [ kwargs[key] ] + tmpArgs[key]
		del tmpArgs
		if "self" in kwargs.keys(): #self is reserved for bound methods
			raise errors.BadRequest()
		#Parse the URL
		path = urlparse.urlparse( path ).path
		self.pathlist = [ urlparse.unquote( x ) for x in path.strip("/").split("/") ]
		caller = conf["viur.mainApp"]
		idx = 0 #Count how may items from *args we'd have consumed (so the rest can go into *args of the called func
		for currpath in self.pathlist:
			if "canAccess" in dir( caller ) and not caller.canAccess():
				# We have a canAccess function guarding that object,
				# and it returns False...
				raise( errors.Unauthorized() )
			idx += 1
			currpath = currpath.replace("-", "_").replace(".", "_")
			if currpath in dir( caller ):
				caller = getattr( caller,currpath )
				if (("exposed" in dir( caller ) and caller.exposed) or ("internalExposed" in dir( caller ) and caller.internalExposed and self.internalRequest)) and hasattr(caller, '__call__'):
					args = self.pathlist[ idx : ] + [ x for x in args ] #Prepend the rest of Path to args
					break
			elif "index" in dir( caller ):
				caller = getattr( caller, "index" )
				if (("exposed" in dir( caller ) and caller.exposed) or ("internalExposed" in dir( caller ) and caller.internalExposed and self.internalRequest)) and hasattr(caller, '__call__'):
					args = self.pathlist[ idx-1 : ] + [ x for x in args ]
					break
				else:
					raise( errors.NotFound( "The path %s could not be found" % "/".join( [ ("".join([ y for y in x if y.lower() in "0123456789abcdefghijklmnopqrstuvwxyz"]) ) for x in self.pathlist[ : idx ] ] ) ) )
			else:
				raise( errors.NotFound( "The path %s could not be found" % "/".join( [ ("".join([ y for y in x if y.lower() in "0123456789abcdefghijklmnopqrstuvwxyz"]) ) for x in self.pathlist[ : idx ] ] ) ) )
		if (not callable( caller ) or ((not "exposed" in dir( caller ) or not caller.exposed)) and (not "internalExposed" in dir( caller ) or not caller.internalExposed or not self.internalRequest)):
			if "index" in dir( caller ) \
				and (callable( caller.index ) \
				and ( "exposed" in dir( caller.index ) and caller.index.exposed) \
				or ("internalExposed" in dir( caller.index ) and caller.index.internalExposed and self.internalRequest)):
					caller = caller.index
			else:
				raise( errors.MethodNotAllowed() )
		# Check for forceSSL flag
		if not self.internalRequest \
			and "forceSSL" in dir( caller ) \
			and caller.forceSSL \
			and not self.request.host_url.lower().startswith("https://") \
			and not "Development" in os.environ['SERVER_SOFTWARE']:
				raise( errors.PreconditionFailed("You must use SSL to access this ressource!") )
		# Check for forcePost flag
		if "forcePost" in dir( caller ) and caller.forcePost and not self.isPostRequest:
			raise( errors.MethodNotAllowed("You must use POST to access this ressource!") )
		self.args = []
		for arg in args:
			if isinstance( x, unicode):
				self.args.append( arg )
			else:
				try:
					self.args.append( arg.decode("UTF-8") )
				except:
					pass
		self.kwargs = kwargs
		# Check if this request should bypass the caches
		if self.request.headers.get("X-Viur-Disable-Cache"):
			from server import utils
			#No cache requested, check if the current user is allowed to do so
			user = utils.getCurrentUser()
			if user and "root" in user["access"]:
				logging.debug( "Caching disabled by X-Viur-Disable-Cache header" )
				self.disableCache = True
		try:
			if (conf["viur.debug.traceExternalCallRouting"] and not self.internalRequest) or conf["viur.debug.traceInternalCallRouting"]:
				logging.debug("Calling %s with args=%s and kwargs=%s" % (str(caller),unicode(args), unicode(kwargs)))
			self.response.out.write( caller( *self.args, **self.kwargs ) )
		except TypeError as e:
			if self.internalRequest: #We provide that "service" only for requests originating from outside
				raise
			#Check if the function got too few arguments and raise a NotAcceptable error
			tmpRes = {}
			argsOrder = list( caller.__code__.co_varnames )[ 1 : caller.__code__.co_argcount ]
			# Map default values in
			reversedArgsOrder = argsOrder[ : : -1]
			for defaultValue in list( caller.func_defaults or [] )[ : : -1]:
				tmpRes[ reversedArgsOrder.pop( 0 ) ] = defaultValue
			del reversedArgsOrder
			# Map args in
			setArgs = [] # Store a list of args already set by *args
			for idx in range(0, min( len( args ), len( argsOrder ) ) ):
				setArgs.append( argsOrder[ idx ] )
				tmpRes[ argsOrder[ idx ] ] = args[ idx ]
			# Last, we map the kwargs in
			for k,v in kwargs.items():
				if k in setArgs: #This key has already been set by *args
					raise( errors.NotAcceptable() ) #We reraise that exception as we got duplicate arguments
				tmpRes[ k ] = v
			# Last check, that every parameter is satisfied:
			if not all ( [ x in tmpRes.keys() for x in argsOrder ] ):
				raise( errors.NotAcceptable() )
			raise


	def saveSession(self):
		session.current.save( self )


def setup( modules, render=None, default="jinja2" ):
	"""
		Define whats going to be served by this instance.

		:param config: Usually the module provided as *modules* directory within the application.
		:type config: module | object
		:param renders: Usually the module *server.renders*, or a dictionary renderName => renderClass.
		:type renders: module | dict
		:param default: Name of the renderer, which will form the root of the application.\
		This will be the renderer, which wont get a prefix, usually jinja2. \
		(=> /user instead of /jinja2/user)
		:type default: str
	"""
	import skeletons
	from server.skeleton import Skeleton
	from server.bones import bone

	conf["viur.skeletons"] = {}
	for modelKey in dir( skeletons ):
		skelCls = getattr( skeletons, modelKey )
		for key in dir( skelCls ):
			skel = getattr( skelCls, key )
			try:
				isSkelClass = issubclass( skel, Skeleton )
			except TypeError:
				continue
			if isSkelClass:
				if not skel.kindName:
					# Looks like a common base-class for skeletons
					continue
				if skel.kindName in conf["viur.skeletons"].keys() and skel!=conf["viur.skeletons"][ skel.kindName ]:
					# We have a conflict here, lets see if one skeleton is from server.*, and one from skeletons.*
					relNewFileName = inspect.getfile(skel).replace( os.getcwd(),"" )
					relOldFileName = inspect.getfile(conf["viur.skeletons"][ skel.kindName ]).replace( os.getcwd(),"" )
					if relNewFileName.strip(os.path.sep).startswith("server"):
						#The currently processed skeleton is from the server.* package
						continue
					elif relOldFileName.strip(os.path.sep).startswith("server"):
						#The old one was from server - override it
						conf["viur.skeletons"][ skel.kindName ] = skel
						continue
					raise ValueError("Duplicate definition for %s" % skel.kindName)
				conf["viur.skeletons"][ skel.kindName ] = skel
	if not render:
		import server.render
		render = server.render
	conf["viur.mainApp"] = buildApp( modules, render, default )
	renderPrefix = [ "/%s" % x for x in dir( render ) if (not x.startswith("_") and x!=default) ]+[""]
	conf["viur.wsgiApp"] = webapp.WSGIApplication( [(r'/(.*)', BrowseHandler)] )
	bone.setSystemInitialized()
	runStartupTasks() #Add a deferred call to run all queued startup tasks
	return( conf["viur.wsgiApp"] )
	

def run():
	"""
		Runs the previously configured server.
	"""
	run_wsgi_app( conf["viur.wsgiApp"] )

## Decorators ##
def forceSSL( f ):
	"""
		Decorator, which forces usage of an encrypted Cchannel for a given resource.
		Has no effects on development-servers.
	"""
	f.forceSSL = True
	return( f )

def forcePost( f ):
	"""
		Decorator, which forces usage of an http post request.
	"""
	f.forcePost = True
	return( f )

def exposed( f ):
	"""
		Decorator, which marks an function as exposed.

		Only exposed functions are callable by http-requests.
	"""
	f.exposed = True
	return( f )

def internalExposed( f ):
	"""
		Decorator, marks an function as internal exposed.

		Internal exposed functions are not callable by external http-requests,
		but can be called by templates using ``execRequest()``.
	"""
	f.internalExposed = True
	return( f )
