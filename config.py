# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from google.appengine.ext import db
from google.appengine.api import memcache
import sys

apiVersion = 1 #What format do we use to store data in the bigtable

#Conf is static, local Dictionary. Changes here are local to the current instance
conf = {
	"bugsnag.apiKey": None, #If set, ViUR will report Errors to bugsnag

	"viur.accessRights": ["root","admin"],  #Accessrights available on this Application
	"viur.availableLanguages": [], #List of language-codes, which are valid for this application

	"viur.cacheEnvironmentKey": None, #If set, this function will be called for each cache-attempt and the result will be included in the computed cache-key
	"viur.capabilities": [], #Extended functionality of the whole System (For module-dependend functionality advertise this in the module configuration (adminInfo)
	"viur.contentSecurityPolicy": None, #If set, viur will emit a CSP http-header with each request. Use the csp module to set this property

	"viur.db.caching" : 2, #Cache strategy used by the database. 2: Aggressive, 1: Safe, 0: Off
	"viur.debug.traceExceptions": False, #If enabled, user-generated exceptions from the server.errors module won't be caught and handled
	"viur.debug.traceExternalCallRouting": True, #If enabled, ViUR will log which (exposed) function are called from outside with what arguments
	"viur.debug.traceInternalCallRouting": True, #If enabled, ViUR will log which (internal-exposed) function are called from templates with what arguments
	"viur.debug.traceQueries": True, #If enabled, we log all datastore queries performed
	"viur.defaultLanguage": "en", #Unless overridden by the Project: Use english as default language
	"viur.disableCache": False, #If set to true, the decorator @enableCache from server.cache has no effect
	"viur.domainLanguageMapping": {},  #Maps Domains to alternative default languages

	"viur.emailRecipientOverride": False, #If set, all outgoing emails will be send to this address (overriding the 'dests'-parameter in utils.sendEmail)
	"viur.emailSenderOverride": False, #If set, this sender will be used, regardless of what the templates advertise as sender
	"viur.errorHandler": None, #If set, ViUR call this function instead of rendering the viur.errorTemplate if an exception occurs
	"viur.errorTemplate": "server/template/error.html", #Path to the template to render if an unhandled error occurs. This is a Python String-template, *not* a jinja2 one!
	"viur.exportPassword": None, # Activates the Database export API if set. Must be exactly 32 chars. *Everyone* knowing this password can dump the whole database!

	"viur.forceSSL": False,  #If true, all requests must be encrypted (ignored on development server)

	"viur.importPassword": None, # Activates the Database import API if set. Must be exactly 32 chars. *Everyone* knowing this password can rewrite the whole database!

	"viur.languageAliasMap": {}, #Allows mapping of certain languages to one translation (ie. us->en)
	"viur.languageMethod": "session", #Defines how translations are applied. session: Per Session, url: inject language prefix in url, domain: one domain per language
	"viur.logMissingTranslations": False, #If true, ViUR will log missing translations in the datastore

	"viur.mainApp": None,  #Reference to our pre-build Application-Instance
	"viur.maxPasswordLength": 512, #Prevent Denial of Service attacks using large inputs for pbkdf2
	"viur.maxPostParamsCount": 250, #Upper limit of the amount of parameters we accept per request. Prevents Hash-Collision-Attacks
	"viur.models": None, #Dictionary of all models known to this instance

	"viur.noSSLCheckUrls": ["/_tasks*", "/ah/*"], #List of Urls for which viur.forceSSL is ignored. Add an asterisk to mark that entry as a prefix (exact match otherwise)

	"viur.requestPreprocessor": None, # Allows the application to register a function that's called before the request gets routed

	"viur.salt": "ViUR-CMS",  #Default salt which will be used for eg. passwords. Once the application is used, this must not change!
	"viur.searchValidChars": "abcdefghijklmnopqrstuvwxyz0123456789",  #Characters valid for the internal search functionality (all other chars are ignored)
	"viur.security.contentSecurityPolicy": None, #If set, viur will emit a CSP http-header with each request. Use security.addCspRule to set this property
	"viur.security.strictTransportSecurity": None, #If set, viur will emit a HSTS http-header with each request. Use security.enableStrictTransportSecurity to set this property
	"viur.security.publicKeyPins": None, #If set, viur will emit a Public Key Pins http-header with each request. Use security.setPublicKeyPins to set this property
	"viur.session.lifeTime": 60*60, #Default is 60 minutes lifetime for ViUR sessions
	"viur.session.persistentFieldsOnLogin": [], #If set, these Fields will survive the session.reset() called on user/login
	"viur.session.persistentFieldsOnLogout": [], #If set, these Fields will survive the session.reset() called on user/logout

	"viur.tasks.startBackendOnDemand": True #If true, allows the task module to start a backend immediately (instead of waiting for the cronjob)
}


class SharedConf():
	"""
		The *SharedConf* is shared between **ALL** instances of the application.

		For access, the singleton ``sharedConf`` should be used instead of instancing this class.
		It takes up to 60 Seconds before changes get visible on all instances.

		:warning: Changes here are replicated between **ALL** instances!\
		Don't use this feature for real-time, high-traffic inter-instance communication.
	"""
	class SharedConfData( db.Expando ): # DB-Representation 
		pass

	data = {
		"viur.disabled": False,
		"viur.apiVersion": apiVersion
	}

	ctime = datetime(2000, 1, 1, 0, 0, 0)
	updateInterval = timedelta(seconds=60) #Every 60 Secs
	keyName = "viur-sharedconf"
	
	def __init__(self):
		disabled = self["viur.disabled"] #Read the config if it exists
	
	def __getitem__(self, key):
		currTime = datetime.now()
		if currTime>self.ctime+self.updateInterval:
			data = memcache.get( self.keyName )
			if data: #Loaded successfully from Memcache
				self.data.update( data )
				self.ctime = currTime
			else:
				data = SharedConf.SharedConfData.get_by_key_name( self.keyName )
				if data:
					for k in data.dynamic_properties():
						self.data[ k ] = getattr( data, k )
				else: #There isnt any config in the db nor the memcache
					data = SharedConf.SharedConfData( key_name=self.keyName )
					for k,v in self.data.items(): #Initialize the DB-Config
						setattr( data, k, v )
					data.put()
				memcache.set( self.keyName, self.data, 60*60*24 )
		return( self.data[ key ] )
		
	def __setitem__(self, key, value ):
		self.data[ key ] = value
		memcache.set( self.keyName, self.data, 60*60*24 )
		data = SharedConf.SharedConfData.get_by_key_name( self.keyName )
		if not data:
			data = SharedConf.SharedConfData( key_name=self.keyName )
			for k,v in self.data.items(): #Initialize the DB-Config
				setattr( data, k, v )
		else:
			setattr( data, key, value )
		data.put()
	

if "viur_doc_build" in dir(sys):
	from mock import MagicMock
	sharedConf = MagicMock()
else:
	sharedConf = SharedConf()
