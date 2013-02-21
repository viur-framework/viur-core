# -*- coding: utf-8 -*-
from google.appengine.api import memcache, app_identity, mail
from google.appengine.ext import ndb, deferred
import new, os
from server.bones import baseBone
from server.session import current
import string, random, base64
from google.appengine.api import search
from server.config import conf
from datetime import datetime, timedelta
import logging

classCache = {}

class Expando( ndb.Model ):
	"""
		Warning. If u dont need the caching provided by ndb for ur project - dont use its api.
		Currently its broken in every corner u look at, and totally inconsistent.
		Here, we have to copy the whole Expando-Claas, just to fix 4 Lines!!!
	"""
	_default_indexed = True

	def _set_attributes(self, kwds):
		for name, value in kwds.iteritems():
			setattr(self, name, value)

	@classmethod
	def _unknown_projection(cls, name):
		# It is not an error to project on an unknown Expando property.
		pass

	def __getattr__(self, name):
		if name.startswith('_'):
			return super(Expando, self).__getattr__(name)
		prop = self._properties.get(name)
		if prop is None:
			return super(Expando, self).__getattribute__(name)
		return prop._get_value(self)

	def __setattr__(self, name, value): #Monkey-Patching the setattr function, so it accepts texts > 500 bytes
		if (name.startswith('_') or
			isinstance(getattr(self.__class__, name, None), (ndb.Property, property))):
			return super(Expando, self).__setattr__(name, value)
		# TODO: Refactor this to share code with _fake_property().
		self._clone_properties()
		if isinstance(value, ndb.Model):
			prop = ndbStructuredProperty(ndb.Model, name)
		else:
			repeated = isinstance(value, list)
			indexed = self._default_indexed
			# TODO: What if it's a list of Model instances?
			if isinstance( value, basestring) and len( value )> 490: #<< Do our magic here: Allow TextProperties in Expando
				prop = ndb.TextProperty(name, repeated=repeated )
			elif isinstance(value, list) and all( [isinstance( x, basestring ) for x in value] ) and any( [ len(x)>490 for x in value ] ):
				prop = ndb.TextProperty(name, repeated=repeated)
			else:
				prop = ndb.GenericProperty(name, repeated=repeated, indexed=indexed)
		prop._code_name = name
		self._properties[name] = prop
		prop._set_value(self, value)

	def __delattr__(self, name):
		if (name.startswith('_') or isinstance(getattr(self.__class__, name, None), (ndb.Property, property))):
			return super(Expando, self).__delattr__(name)
		prop = self._properties.get(name)
		if not isinstance(prop, Property):
			raise TypeError('Model properties must be Property instances; not %r' % prop)
		prop._delete_value(self)
		if prop in self.__class__._properties:
			raise RuntimeError('Property %s still in the list of properties for the base class.' % name)
		del self._properties[name]

def generateExpandoClass( className ):
	"""Creates a new Appengine Expando Class which operates on the collection specified by className.
	
	@type className: String
	@param className: Name of the collection
	@returns: An Appengine Expando Class
	"""
	assert False
	global classCache
	if not className in classCache.keys():
		classCache[ className ] = new.classobj( className, ( Expando,), {})
	return( classCache[ className ] )
	
def buildDBFilter( skel, rawFilter ):
	""" Creates an Appengine Query Class for the given Skeleton and Filters.
	Its safe to direcly pass the parameters submitted from the client, all nonsensical Parameters (regarding to the Skeleton) are discarded.
	
	@type skel: Skeleton
	@param skel: Skeleton to apply the filter to
	@type rawFilter: Dict
	@param rawFilter: Filter to apply on the data. May be empty (Safe defaults are choosen in this case)
	@returns: A new Appengine Query Class
	"""
	limit = 20
	cursor = None
	dbFilter = generateExpandoClass( skel.entityName ).query()
##
	if skel.searchIndex and "search" in rawFilter.keys(): #We perform a Search via Google API - all other parameters are ignored
		searchRes = search.Index( name=skel.searchIndex ).search( query=search.Query( query_string=rawFilter["search"], options=search.QueryOptions( limit=25 ) ) )
		tmpRes = [ ndb.Key(urlsafe=x.doc_id[ 2: ] ) for x in searchRes ]
		if tmpRes: #Again.. Workaround for broken ndb API: Filtering IN using an empty list: exception instead of empty result
			res = dbFilter.filter(  generateExpandoClass( dbFilter.kind )._key.IN( tmpRes ) )
		else:
			res = dbFilter.filter(  ndb.GenericProperty("_-Non-ExIstIng_-Property_-" ) == None )
		res = res.order( skel._expando._key )
		res.limit = limit
		res.cursor = None
		return( res )
	for key in dir( skel ):
		bone = getattr( skel, key )
		if not "__" in key and isinstance( bone , baseBone ):
			dbFilter = bone.buildDBFilter( key, skel, dbFilter, rawFilter )
			dbFilter = bone.buildDBSort( key, skel, dbFilter, rawFilter )
	if "search" in rawFilter.keys():
		if isinstance( rawFilter["search"], list ):
			taglist = [ "".join([y for y in unicode(x).lower() if y in conf["viur.searchValidChars"] ] ) for x in rawFilter["search"] ]
			if taglist: #NDB BUG
				dbFilter = dbFilter.filter( ndb.GenericProperty("viur_tags").IN( taglist ) )
			else:
				dbFilter = dbFilter.filter(  ndb.GenericProperty("_-Non-ExIstIng_-Property_-" ) == None )
		else:
			taglist = [ "".join([y for y in unicode(x).lower() if y in conf["viur.searchValidChars"] ]) for x in unicode(rawFilter["search"]).split(" ")] 
			if taglist:
				dbFilter = dbFilter.filter( ndb.GenericProperty("viur_tags").IN (taglist) )
			else:
				dbFilter = dbFilter.filter(  ndb.GenericProperty("_-Non-ExIstIng_-Property_-" ) == None )
	if "cursor" in rawFilter.keys() and rawFilter["cursor"] and rawFilter["cursor"].lower()!="none":
		cursor = ndb.Cursor( urlsafe=rawFilter["cursor"] )
	if "amount" in list(rawFilter.keys()) and str(rawFilter["amount"]).isdigit() and int( rawFilter["amount"] ) >0 and int( rawFilter["amount"] ) <= 50:
		limit = int(rawFilter["amount"])
	if "postProcessSearchFilter" in dir( skel ):
		dbFilter = skel.postProcessSearchFilter( dbFilter, rawFilter )
	if not dbFilter.orders: #And another NDB fix
		dbFilter = dbFilter.order( skel._expando._key )

##
	dbFilter.limit = limit
	dbFilter.cursor = cursor
	return( dbFilter )


def generateRandomString( length=13 ):
	"""Returns a new random String of the given length.
	Its safe to use this string in urls or html.
	
	@type length: Int
	@name length: Length of the generated String
	@return: A new random String of the given length
	"""
	return(  ''.join( [ random.choice(string.ascii_lowercase+string.ascii_uppercase + string.digits) for x in range(13) ] ) )

def createSecurityKey( duration=None, **kwargs ):
	"""
		Creates a new onetime Securitykey for the current session
		If duration is not set, this key is valid only for the current session.
		Otherwise, the key and its data is serialized and saved inside the datastore
		for up to duration-seconds
		@param duration: Make this key valid for a fixed timeframe (and independend of the current session)
		@type duration: Int or None
		@returns: The new onetime key
		
		Fixme: We have a race-condition here.
		If the user issues two requests at the same time, its possible that a freshly generated skey is lost
		or a skey consumed by one of these requests become avaiable again
	"""
	key = generateRandomString()
	if duration: #Create a longterm key in the datastore
		dbObj = generateExpandoClass("viur_security_keys" )()
		for k, v in kwargs.items():
			setattr( dbObj, k, v )
		dbObj.duration = datetime.now()+timedelta( seconds=duration )
		dbObj.skey = key
		dbObj.put()
	else: #Create an session-dependet key
		keys = current.get( "skeys" )
		if not keys:
			keys = []
		keys.append( key )
		if len( keys )> 100:
			keys = keys[ -100: ]
		current["skeys"] = keys
		current.markChanged()
	return( key )
	
def validateSecurityKey( key, isLongTermKey=False ):
	""" Validates a onetime securitykey for the current session
	
	@type key: String
	@param key: The key to validate
	@param isLongTermKey: Must be true, if the key was created with a fixed validationtime ,false otherwise
	@returns: If not isLongTermKey: True on success, False otherwise. If isLongTermKey, the stored data will be returned as dict on success
	"""
	if isLongTermKey:
		dbObj = generateExpandoClass("viur_security_keys" ).query().filter( ndb.GenericProperty("skey") == key ).get()
		if dbObj:
			res ={}
			for k in dbObj._properties.keys():
				res[ k ] = getattr( dbObj, k )
			dbObj.key.delete()
			return( res )
	else:
		keys = current.get( "skeys" )
		if keys and key in keys:
			keys.remove( key )
			current["skeys"] = keys
			current.markChanged()
		return( True )
	return( False )
	
def sendEMail( dests, name , skel, extraFiles=[] ):
	"""Sends an EMail
	
	@type dests: String or [String]
	@param dests: EMail-Address (or list of Addresses) to send the mail to
	@type name: String
	@param name: Template (as String) or the filename to a template
	@type skel: Skeleton or Dict or None
	@param skel: Data made avaiable to the template. In case of a Skeleton it's parsed the usual way; Dictionarys are passed unchanged
	@type extraFiles: [open fileobjects]
	@param extraFiles: List of fileobjects to send within the mail as attachments
	"""
	from server import conf
	headers, data = conf["viur.emailRenderer"]( skel, name, dests )
	xheader = {}
	if "references" in headers.keys():
		xheader["References"] = headers["references"]
	if "in-reply-to" in headers.keys():
		xheader["In-Reply-To"] = headers["in-reply-to"]	
	if xheader:
		message = mail.EmailMessage(headers=xheader)
	else:
		message = mail.EmailMessage()
	#container['Date'] = datetime.today().strftime("%a, %d %b %Y %H:%M:%S %z")
	mailfrom = "viur@%s.appspotmail.com" % app_identity.get_application_id()
	if "subject" in headers.keys():
		message.subject =  "=?utf-8?B?%s?=" % base64.b64encode( headers["subject"].encode("UTF-8") )
	else:
		message.subject = "No Subject"
	if "from" in headers.keys():
		mailfrom = headers["from"]
	if conf["viur.emailSenderOverride"]:
		mailfrom = conf["viur.emailSenderOverride"]
	if isinstance( dests, list ):
		message.to = ", ".join( dests )
	else:
		message.to = dests
	message.sender = mailfrom
	message.html = data.encode('ascii', 'xmlcharrefreplace')
	if len( extraFiles )> 0:
		message.attachments = extraFiles
	message.send( )

def sendEMailToAdmins( subject, body, sender=None ):
	"""
		Sends an email to all admins of the current application. 
		(all users having access to the applications dashboard)
		
		@param subject: Subject of the message
		@type subject: string
		@param body: Message Body
		@type body: string
		@param sender: (optional) specify a differend sender
		@type sender: string
	"""
	if not sender:
		sender = "viur@%s.appspotmail.com" % app_identity.get_application_id()
	mail.send_mail_to_admins( sender, "=?utf-8?B?%s?=" % base64.b64encode( subject.encode("UTF-8") ), body.encode('ascii', 'xmlcharrefreplace') )

def getCurrentUser( ):
	"""
		Helper which returns the current user for the current request (if any)
	"""
	user = None
	if "user" in dir( conf["viur.mainApp"] ): #Check for our custom user-api
		user = conf["viur.mainApp"].user.getCurrentUser()
	return( user )

def markFileForDeletion( dlkey ):
	"""
	Adds a marker to the DB that the file might can be deleted.
	Once the mark has been set, the db is checked four times (default: every 4 hours)
	if the file is in use anywhere. If it is, the mark gets deleted, otherwise
	the mark and the file are removed from the DB. These delayed checks are necessary
	due to database inconsistency.
	
	@type dlkey: String
	@param dlkey: Downloadkey of the file
	"""
	expurgeClass = generateExpandoClass( "viur-deleted-files" )
	fileObj = expurgeClass.query().filter( ndb.GenericProperty("dlkey") == dlkey ).get()
	if fileObj: #Its allready marked
		return
	fileObj = expurgeClass( itercount = 0, dlkey = str( dlkey ) )
	fileObj.put()


