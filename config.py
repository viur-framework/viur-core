# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from google.appengine.ext import db
from google.appengine.api import memcache

#Conf is static, local Dictionary. Changes here are local to the current instance
conf = {	"viur.mainApp": None,  #Reference to our prebuild Application-Instance
		"viur.models": None, #Dictionary of all models known to this instance
		"viur.defaultLanguage": "en", #Unless overridden by the Project: Use english as default language
		"viur.languageMethod": "session", #Defines how translations are applied. session: Per Session, url: inject language prefix in url, domain: one domain per language
		"viur.domainLanguageMapping": {},  #Maps Domains to alternative default languages
		"viur.avaiableLanguages": [], #List of language-codes, which are valid for this application
		"viur.languageAliasMap": {}, #Allows mapping of certain languages to one translation (ie. us->en)
		"viur.capabilities": [], #Extended functionality of the whole System (For modul-dependend functionality advertise this in the modul configuration (adminInfo)
		"viur.searchValidChars": "abcdefghijklmnopqrstuvwxyz0123456789",  #Characters valid for the internal search functionality (all other chars are ignored)
		"viur.accessRights": ["root","admin"],  #Accessrights available on this Application
		"viur.salt": "ViUR-CMS",  #Default salt which will be used for eg. passwods. Once the application is used, this must not change!
		"viur.maxPostParamsCount": 250, #Upper limit of the amount of parameters we accept per request. Prevents Hash-Collision-Attacks
		"viur.forceSSL": False,  #If true, all requests must be encrypted (ignored on development server)
		"viur.emailSenderOverride": False, #If set, this sender will be used, regardless of what the templates advertise as sender
		"viur.db.caching" : 2, #Cache strategy used by the database. 2: Aggressive, 1: Safe, 0: Off
		"viur.tasks.startBackendOnDemand": True, #If true, allows the task modul to start a backend immediately (instead of waiting for the cronjob)
		"viur.logMissingTranslations": False, #If true, ViUR will log missing translations in the datastore
		"viur.disableCache": False, #If set to true, the decorator @enableCache from server.cache has no effect
		"viur.maxPasswordLength": 512, #Prevent Denial of Service attacks using large inputs for pbkdf2
		"viur.exportPassword": None, # Activates the Database export API if set. Must be exactly 32 chars. *Everyone* knowing this password can dump the whole database!
		"viur.importPassword": None, # Activates the Database import API if set. Must be exactly 32 chars. *Everyone* knowing this password can rewrite the whole database!
		"viur.debug.traceExceptions": False, #If enabled, user-generated exceptions from the server.errors module won't be caught and handled
		"viur.debug.traceExternalCallRouting": True, #If enabled, ViUR will log which (exposed) function are called from outside with what arguments
		"viur.debug.traceInternalCallRouting": True, #If enabled, ViUR will log which (internal-exposed) function are called from templates with what arguments
                "viur.debug.traceQueries": True, #If enabled, we log all datastore queries performed
		"bugsnag.apiKey": None #If set, ViUR will report Errors to bugsnag
	}


class SharedConf(  ):
	"""
		SharedConf is shared between *ALL* instances of the appication.
		Changes here are replicated beween *ALL* instances!
		Dont use this for real-time, high-traffic inter-instance communication;
		it takes up to 60 Seconds before changes get visible on all instances.
		Use the singleton sharedConf instead of instancing this Class.
	"""
	class SharedConfData( db.Expando ): # DB-Representation 
		pass

	data = {	"viur.disabled": False, 
			"viur.apiVersion": 0
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
	
	
sharedConf = SharedConf()

