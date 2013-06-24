"""
ViUR Server

Copyright 2012 Mausbrand Informationssysteme GmbH
Licensed under LGPL Version 3.
http://www.gnu.org/licenses/lgpl-3.0

http://www.viur.is
"""
import sys, traceback, os
#All (optional) 3rd-party modules in our libs-directory
for lib in os.listdir( os.path.join("server", "libs") ):
	if not lib.lower().endswith(".zip"): #Skip invalid file
		continue
	sys.path.insert(0, os.path.join( "server", "libs", lib ) )
from server.config import conf, sharedConf
from server import request
import server.languages as servertrans
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import deferred
from google.appengine.api import users
import urlparse

from functools import wraps
from string import Template
from StringIO import StringIO
import logging

### Multi-Language Part
try:
	import translations
	conf["viur.avaiableLanguages"].extend( [x for x in dir( translations ) if (len(x)==2 and not x.startswith("_")) ] )
except: #The Project doesnt use Multi-Language features
	translations = None
def translate( key, **kwargs ):
	try:
		lang = request.current.get().language
	except:
		return( key )
	lang = lang or conf["viur.defaultLanguage"]
	if lang in conf["viur.languageAliasMap"].keys():
		lang = conf["viur.languageAliasMap"][ lang ]
	if lang and lang in dir( translations ):
		langDict = getattr(translations,lang)
		if key.lower() in langDict.keys():
			return( langDict[ key.lower() ] )
	if lang and lang in dir( servertrans ):
		langDict = getattr(servertrans,lang)
		if key.lower() in langDict.keys():
			return( langDict[ key.lower() ] )
	if conf["viur.logMissingTranslations"]:
		from server import db
		db.GetOrInsert( key="%s-%s" % (key, str(lang)), kindName="viur-missing-translations", langkey=key, lang=lang )
	for k, v in kwargs.items():
		key = key.replace("{{%s}}"%k, v )
	return( key )
__builtins__["_"] = translate #Install the global "_"-Function

def setDefaultLanguage( lang ):
	conf["viur.defaultLanguage"] = lang.lower()

def setDefaultDomainLanguage( domain, lang ):
	host = domain.lower().strip(" /")
	if host.startswith("www."):
		host = host[ 4: ]
	conf["viur.domainLanguageMapping"][host] = lang.lower()

### Multi-Language Part: END 

from server import session, errors
from server.tasks import TaskHandler
from server import backup

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
		This creates the application-context for the current instance.
		It converts the classes found in your "modules"-modul, and the given
		renders into the object found at conf["viur.mainApp"].
		Each class found in "modules" will be
			- instanciated
			- get the corresponding render attached
			- attached to conf["viur.mainApp"]
		@param config: Usually your "modules"-modul.
		@type config: Modul, or anything else which can be traversed by dir, getattr
		@param renders: Usually the module server.renders.
		@type renders: Modul, or a dictionary renderName => renderClass
		@param default: Name of the render, wich will form the root of the application (i.e. the render, which wont get a prefix.) Usually jinja2. ( => /user instead of /jinja2/user )
		@type default: String
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
	for modulName in dir( config ): # iterate over all modules
		if modulName=="index":
			continue
		for renderName in list(rendlist.keys()): # look, if a particular render should be built
			if renderName in dir( getattr( config, modulName ) ) \
				and getattr( getattr( config, modulName ) , renderName ):
					modulPath = "%s/%s" % ("/"+renderName if renderName!=default else "",  modulName)
					obj =  getattr( config,  modulName)( modulName, modulPath )
					if modulName in rendlist[ renderName ]: # we have a special render for this
						obj.render = rendlist[ renderName ][ modulName ]( parent = obj )
					else: # Attach the default render
						obj.render = rendlist[ renderName ][ "default" ]( parent = obj )
					setattr(obj,"_modulName",modulName)
					if renderName == default: #default or render (sub)namespace?
						setattr( res,  modulName, obj )
					else:
						if not renderName in dir( res ): 
							if "_rootApp" in rendlist[renderName]:
								obj = rendlist[renderName]["_rootApp"]()
								obj.render = rendlist[renderName]["default"]
								setattr( res,  renderName,  buildObject(rendlist[renderName]["_rootApp"], rendlist[renderName]["default"]) )
							else:
								setattr( res,  renderName,  ExtendableObject() )
						setattr( getattr(res, renderName), modulName, obj )
	if not isinstance( renderers,    dict ): # Apply Renderers postProcess Filters
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
	if default in rendlist and "renderEmail" in dir (rendlist[ default ]["default"]()):
		conf["viur.emailRenderer"] = rendlist[ default ]["default"]().renderEmail
	elif "jinja2" in list(rendlist.keys()):
		conf["viur.emailRenderer"] = rendlist[ "jinja2" ]["default"]().renderEmail
	return res

class BrowseHandler(webapp.RequestHandler):
	"""
		This class accepts the requests, collect its parameters and
		routes the request to its destination function.
		Dont mess around with. Dont instanciate. Dont subclass.
		DONT TOUCH!
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
					if lng in conf["viur.avaiableLanguages"]+list( conf["viur.languageAliasMap"].keys() ):
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
			if len( tmppath )>0 and tmppath[0] in conf["viur.avaiableLanguages"]+list( conf["viur.languageAliasMap"].keys() ):
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
		if sharedConf["viur.disabled"] and not (users.is_current_user_admin() or "HTTP_X_QUEUE_NAME".lower() in [x.lower() for x in os.environ.keys()] ): #FIXME: Validate this works
			self.response.set_status( 503 ) #Service unaviable
			tpl = Template( open("server/template/error.html", "r").read() )
			if isinstance( sharedConf["viur.disabled"], basestring ):
				msg = sharedConf["viur.disabled"]
			else:
				msg = "This application is currently disabled or performing maintenance. Try again later."
			self.response.out.write( tpl.safe_substitute( {"error_code": "503", "error_name": "Service unaviable", "error_descr": msg} ) )
			return
		if conf["viur.forceSSL"] and not self.isDevServer and not self.isSSLConnection:
			#Redirect the user to the startpage (using ssl this time)
			host = self.request.host_url.lower()
			host = host[ host.find("://")+3: ].strip(" /") #strip http(s)://
			self.redirect( "https://%s/" % host )
		try:
			session.current.load( self ) # self.request.cookies )
			path = self.selectLanguage( path )
			self.findAndCall( path, *args, **kwargs )
		except errors.Redirect as e :
			self.redirect( e.url.encode("UTF-8") )
		except errors.HTTPException as e:
			self.response.clear()
			self.response.set_status( e.status )
			tpl = Template( open("server/template/error.html", "r").read() )
			self.response.out.write( tpl.safe_substitute( {"error_code": e.status, "error_name":e.name, "error_descr": e.descr} ) )
		except Exception as e: #Something got really wrong
			logging.exception( "Viur caught an unhandled exception!" )
			self.response.clear()
			self.response.set_status( 500 )
			tpl = Template( open("server/template/error.html", "r").read() )
			descr = "The server encountered an unexpected error and is unable to process your request."
			if self.isDevServer: #Were running on development Server
				strIO = StringIO()
				traceback.print_exc(file=strIO)
				descr= strIO.getvalue()
				descr = descr.replace("<","&lt;").replace(">","&gt;").replace(" ", "&nbsp;").replace("\n", "<br />")
			self.response.out.write( tpl.safe_substitute( {"error_code": "500", "error_name":"Internal Server Error", "error_descr": descr} ) )
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
		request.current.setRequest( self )
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
		self.response.out.write( caller( *self.args, **self.kwargs ) )


	def saveSession(self):
		session.current.save( self )


def setup( modules, render=None, default="jinja2" ):
	"""
		Define whats going to be served by this instance.
		@param modules: Your "modules"-modul. (The thing you got by calling "import modules")
		@type modules: Modul
		@param render: Usually the "server.renders"-Modul. Allows the project to supply an alternative set of renders
		@type render: Modul, or a dictionary renderBaseName => { renderSubName => Class }, or None (for the build-in set of renders)
		@param default: Which render should be the default. Its modules wont get a prefix (i.e /user instead of /renderBaseName/user )
		@type default: String
	"""
	if not render:
		import server.render
		render = server.render
	conf["viur.mainApp"] = buildApp( modules, render, default )
	renderPrefix = [ "/%s" % x for x in dir( render ) if (not x.startswith("_") and x!=default) ]+[""]
	conf["viur.wsgiApp"] = webapp.WSGIApplication( [(r'/(.*)', BrowseHandler)] )
	return( conf["viur.wsgiApp"] )
	

def run( ):
	"""
		Starts processing requests.
	"""
	run_wsgi_app( conf["viur.wsgiApp"] )

## Decorators ##
def forceSSL( f ):
	"""
		Forces usage of an encrypted Channel for a given Ressource.
		Has no effect on the development-server.
	"""
	f.forceSSL = True
	return( f )

def forcePost( f ):
	"""
		Forces usage of an http post request.
	"""
	f.forcePost = True
	return( f )

def exposed( f ):
	"""
		Marks an function as exposed.
		Only exposed functions are callable by http-requests.
	"""
	f.exposed = True
	return( f )

def internalExposed( f ):
	"""
		Marks an function as internal exposed.
		Internal exposed functions are not callable by external http-requests,
		but can be called by templates using execRequest
	"""
	f.internalExposed = True
	return( f )
