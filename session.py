# -*- coding: utf-8 -*-
import threading
import json, pickle
import base64
import string, random
from time import time
from server.tasks import PeriodicTask, callDeferred
from server import db
from server.config import conf
from google.appengine.runtime.apiproxy_errors import CapabilityDisabledError, OverQuotaError
import logging

"""
	Provides a fast and reliable session implementation for the Google AppEngine™.
	Import singleton ``current`` to access the currently active session.

	Example:

	.. code-block:: python

		from session import current as currentSession

		currentSession["your_key"] = "your_data"
		data = currentSession["your_key"]

	A get-method is provided for convenience.
	It returns None instead of raising an Exception if the key is not found.
"""

class SessionWrapper( threading.local ):
	cookieName = "viurCookie"

	def __init__( self, sessionFactory, *args, **kwargs ):
		super( SessionWrapper, self ).__init__( *args, **kwargs )
		self.factory = sessionFactory

	def load( self, req ):
		if not "session" in dir( self ):
			self.session = self.factory()
		return( self.session.load( req ) )

	def __contains__( self, key ):
		try:
			return( key in self.session )
		except AttributeError:
			return( False )

	def __delitem__(self, key ):
		del self.session[key]

	def __getitem__( self, key ):
		try:
			if key=="skeys":
				r = self.session.get( key )
				assert r is None or isinstance(r,list)
			return( self.session[ key ] )
		except AttributeError:
			return( None )

	def get( self, key ):#fixme
		"""For compatibility with cherrypy"""
		try:
			if key=="skeys":
				r = self.session.get( key )
				assert r is None or isinstance(r,list)
			return( self.session.get( key ) )
		except AttributeError:
			return( None )

	def __setitem__( self, key, item ):
		try:
			if key=="skeys":
				assert item is None or isinstance(item,list)
			self.session[ key ] = item
		except AttributeError:
			pass

	def save(self, req):
		try:
			return( self.session.save( req ))
		except AttributeError:
			return( None )

	def getSessionKey(self, req=None):
		try:
			return( self.session.getSessionKey( req ) )
		except AttributeError:
			return( None )

	def markChanged(self):
		try:
			self.session.markChanged()
		except AttributeError:
			pass

	def reset(self):
		try:
			return( self.session.reset() )
		except AttributeError:
			pass

	def getLanguage( self ):
		try:
			return( self.session.get( "language" ) )
		except AttributeError:
			return( None )

	def setLanguage( self, lang ):
		try:
			self.session[ "language" ] = lang
		except AttributeError:
			pass

	def getSessionSecurityKey(self):
		try:
			return( self.session.getSessionSecurityKey() )
		except AttributeError:
			return( "" )


	def items(self):
		try:
			return( self.session.items() )
		except AttributeError:
			return( [] )


class GaeSession:
	plainCookieName = "viurHttpCookie"
	sslCookieName = "viurSSLCookie"
	kindName = "viur-session"

	"""Store Sessions inside the Big Table/Memcache"""

	def load( self, req ):
		"""
			Initializes the Session.

			If the client supplied a valid Cookie, the session is read
			from the memcache/datastore, otherwise a new, empty session
			will be initialized.
		"""
		self.changed = False
		self.key = None
		self.sslKey = None
		self.sessionSecurityKey = None
		self.session = {}
		if self.plainCookieName in req.request.cookies:
			cookie = req.request.cookies[ self.plainCookieName ]
			try:
				data = db.Get( db.Key.from_path( self.kindName, cookie ) )
			except:
				return( False )
			if data: #Loaded successfully from Memcache
				if data["lastseen"] < time() - conf[ "viur.session.lifeTime" ]:
					# This session is too old
					return( False )

				self.session = pickle.loads( base64.b64decode(data["data"]) )
				self.sslKey = data["sslkey"]
				if "skey" in data:
					self.sessionSecurityKey = data["skey"]
				else:
					self.reset()
				if data["lastseen"] < time()-5*60: #Refresh every 5 Minutes
					self.changed = True
			if req.isSSLConnection and not (self.sslCookieName in req.request.cookies and req.request.cookies[ self.sslCookieName ] == self.sslKey and self.sslKey ):
				if self.sslKey:
					logging.warning("Possible session hijack attempt! Session dropped.")
				self.reset()
				return( False )
			self.key = str( cookie )
			return( True )

	def save(self, req):
		"""
			Writes the session to the memcache/datastore.

			Does nothing, if the session hasn't been changed in the current request.
		"""
		if self.changed:
			serialized = base64.b64encode( pickle.dumps(self.session, protocol=pickle.HIGHEST_PROTOCOL ) )
			self.getSessionKey( req )
			# Get the current user id
			userid = None
			try:
				if "user" in dir( conf["viur.mainApp"] ): #Check for our custom user-api
					userid = conf["viur.mainApp"].user.getCurrentUser()["key"]
			except:
				pass
			try:
				dbSession = db.Entity( self.kindName, name=self.key )
				dbSession["data"] = serialized
				dbSession["sslkey"] = self.sslKey
				dbSession["skey"] = self.sessionSecurityKey
				dbSession["lastseen"] = time()
				dbSession["user"] = str(userid) or "guest" #Store the userid inside the sessionobj, so we can kill specific sessions if needed
				dbSession.set_unindexed_properties( ["data","sslkey" ] )
				db.Put( dbSession )
			except (OverQuotaError, CapabilityDisabledError):
				pass
			req.response.headers.add_header( "Set-Cookie", bytes( "%s=%s; Max-Age=99999; Path=/; HttpOnly" % ( self.plainCookieName, self.key ) ) )
			if req.isSSLConnection:
				req.response.headers.add_header( "Set-Cookie", bytes( "%s=%s; Max-Age=99999; Path=/; Secure; HttpOnly" % ( self.sslCookieName, self.sslKey ) ) )


	def __contains__( self, key ):
		"""
			Returns True if the given *key* is set in the current session.
		"""
		return( key in self.session )

	def __delitem__(self, key ):
		"""
			Removes a *key* from the session.

			This key must exist.
		"""
		del self.session[key]
		self.changed = True

	def __getitem__( self, key ):
		"""
			Returns the value stored under the given *key*.

			The key must exist.
		"""
		return( self.session[ key ] )

	def get( self, key ):
		"""
			Returns the value stored under the given key.

			:param key: Key to retrieve from the session variables.
			:type key: str

			:return: Returns None if the key doesn't exist.
		"""
		if( key in self.session ):
			return( self.session[ key ] )
		else:
			return( None )

	def __setitem__( self, key, item ):
		"""
			Stores a new value under the given key.

			If that key exists before, its value is
			overwritten.
		"""
		self.session[ key ] = item
		self.changed = True

	def markChanged(self):
		"""
			Explicitly mark the current session as changed.
			This will force save() to write into the memcache /
			datastore, even if it belives that this session had
			not changed.
		"""
		self.changed = True

	def reset(self):
		"""
			Invalids the current session and starts a new one.

			This function is especially useful at login, where
			we might need to create an SSL-capable session.

			:warning: Everything (except the current language) is flushed.
		"""
		lang = self.session.get("language")
		if self.key:
			db.Delete(db.Key.from_path(self.kindName, self.key))
		self.key = None
		self.sslKey = None
		self.sessionSecurityKey = None
		self.changed = True
		self.session = {}
		if lang:
			self.session["language"] = lang

	def getSessionKey( self, req=None ):
		"""
			Ensures that the current session is initialized
			and returns its session-key.
		"""
		self.changed = True
		if self.key: # We are already initialized
			return( self.key )
		if req is None:
			from server.request import current
			req = current.get()
		self.key = ''.join(random.choice(string.ascii_lowercase+string.ascii_uppercase + string.digits) for x in range(42))
		if req.isSSLConnection:
			self.sslKey = ''.join(random.choice(string.ascii_lowercase+string.ascii_uppercase + string.digits) for x in range(42))
		else:
			self.sslKey = ""
		self.sessionSecurityKey = ''.join(random.choice(string.ascii_lowercase+string.ascii_uppercase + string.digits) for x in range(13))
		return( self.key )

	def getSessionSecurityKey(self):
		"""
			Returns the security key for this session.
		"""
		if self.sessionSecurityKey:
			return( self.sessionSecurityKey )
		return( "" )

	def items(self):
		"""
			Returns all items in the current session.
		"""
		return( self.session.items() )

@callDeferred
def killSessionByUser( user=None ):
	"""
		Invalidates all active sessions for the given *user*.

		This means that this user is instantly logged out.
		If no user is given, it tries to invalidate **all** active sessions.

		Use "guest" as to kill all sessions not associated with an user.

		:param user: UserID, "guest" or None.
		:type user: str | None
	"""
	logging.error("Invalidating all sessions for %s" % user )
	query = db.Query( GaeSession.kindName )
	if user is not None:
		query.filter( "user =", str(user) )
	for key in query.iter(keysOnly=True):
		db.Delete( key )

@PeriodicTask(60*4)
def startClearSessions():
	"""
		Removes old (expired) Sessions
	"""
	doClearSessions( time() - ( conf[ "viur.session.lifeTime" ] + 300 ), None )

@callDeferred
def doClearSessions( timeStamp, cursor ):
	gotAtLeastOne = False
	query = db.Query( GaeSession.kindName ).filter( "lastseen <", timeStamp )
	for oldKey in query.run(100, keysOnly=True):
		gotAtLeastOne = True
		db.Delete( oldKey )
	newCursor = query.getCursor()
	if gotAtLeastOne and newCursor and newCursor.urlsafe()!=cursor:
		doClearSessions( timeStamp, newCursor.urlsafe() )

current = SessionWrapper( GaeSession )
