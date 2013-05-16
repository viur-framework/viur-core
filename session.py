# -*- coding: utf-8 -*-
import threading
import json, pickle
import base64
import string, random
from time import time
from server.tasks import PeriodicTask
from server import db
from google.appengine.runtime.apiproxy_errors import CapabilityDisabledError, OverQuotaError
import logging

"""
	Provides a fast and reliable Session-Implementation for the GAE.
	Use singleton current to access the current Session.
	Example:
	from session import current as currentSession
	currentSession["your_key"] = "your_data"
	data = currentSession["your_key"]
	
	A get-method is provided for convenience.
	It returns None instead of raising an Exception for the key is not found.
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
			return( key in self.session.keys() ) 
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
		


class GaeSession:
	lifeTime = 60*60 #60 Minutes
	plainCookieName = "viurHttpCookie"
	sslCookieName = "viurSSLCookie"
	kindName = "viur-session"
	
	"""Store Sessions inside the Big Table/Memcache"""
	def load( self, req ):
		"""
			Initializes the Session.
			If the client supplied a valid Cookie,
			the session is read from the memcache/datastore,
			otherwise a new, empty session is initialized.
		"""
		self.changed = False
		self.key = None
		self.sslKey = None
		self.session = {}
		if self.plainCookieName in req.request.cookies.keys():
			cookie = req.request.cookies[ self.plainCookieName ]
			try:
				data = db.Get( db.Key.from_path( self.kindName, cookie ) )
			except:
				return
			if data: #Loaded successfully from Memcache
				if data["lastseen"] < time()-self.lifeTime :
					# This session is too old
					return
				self.session = pickle.loads( base64.b64decode(data["data"]) )
				self.sslKey = data["sslkey"]
				if data["lastseen"] < time()-5*60: #Refresh every 5 Minutes
					self.changed = True
			if req.isSSLConnection and not (self.sslCookieName in req.request.cookies.keys() and req.request.cookies[ self.sslCookieName ] == self.sslKey and self.sslKey ):
				if self.sslKey:
					logging.warning("Possible session hijack attempt! Session dropped.")
				self.reset()
				return
			if self.session:
				self.key = str( cookie )
				return( True )
			else:
				self.session = {}
				return( False )
	
	def save(self, req):
		"""
			Writes the session to the memcache/datastore.
			Does nothing, if the session hasn't been changed
			in the current request.
		"""
		if self.changed:
			serialized = base64.b64encode( pickle.dumps(self.session, protocol=pickle.HIGHEST_PROTOCOL ) )
			if len(serialized)>620000 and len(serialized)<=920000:
				logging.warning("Your session is very large (%s bytes)! It cannot be larger than 900KB!" % len( serialized ) )
			elif len(serialized)>920000:
				logging.critical("Your session stores too much data! Expect failure!")
			self.getSessionKey( req )
			try:
				dbSession = db.Entity( self.kindName, name=self.key )
				dbSession["data"] = serialized
				dbSession["sslkey"] = self.sslKey
				dbSession["lastseen"] = time()
				dbSession.set_unindexed_properties( ["data","sslkey" ] )
				db.Put( dbSession )
			except OverQuotaError, CapabilityDisabledError:
				pass
			req.response.headers.add_header( "Set-Cookie", bytes( "%s=%s; Max-Age=99999; Path=/; HttpOnly" % ( self.plainCookieName, self.key ) ) )
			if req.isSSLConnection:
				req.response.headers.add_header( "Set-Cookie", bytes( "%s=%s; Max-Age=99999; Path=/; Secure; HttpOnly" % ( self.sslCookieName, self.sslKey ) ) )


	def __contains__( self, key ):
		"""
			Returns True if the given key is set in
			the current session.
		"""
		return( key in self.session ) 
	
	def __delitem__(self, key ):
		"""
			Removes a key from the session.
			This key must exist.
		"""
		del self.session[key]
		self.changed = True
	
	def __getitem__( self, key ):
		"""
			Returns the value stored under the
			given key. The key must exist.
		"""
		return( self.session[ key ] )
	
	def get( self, key ): 
		"""
			Returns the value stored under the
			given key. Returns None if the key
			dosnt exist.
		"""
		if( key in self.session.keys() ):
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
			Especially usefull on login, where we might need to
			create an ssl-capable Session.
			Warning: Everything (except the current language)
			is flushed.
		"""
		try:
			lang = self.session[ "language" ]
		except:
			lang = None
		self.key = None
		self.sslKey = None
		self.changed = True
		self.session = {}
		if lang:
			self.session[ "language" ] = lang
			
	def getSessionKey( self, req=None ):
		"""
			Ensures that the current session is initialized
			and returns its session-key
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
		return( self.key )
	
@PeriodicTask( 60 )
def cleanup( ):
	oldSessions = db.Query(GaeSession.kindName).filter("lastseen <", time()-GaeSession.lifeTime ).run(limit=1000,keysOnly=True)
	while( oldSessions ):
		db.Delete( oldSessions )
		oldSessions = db.Query(GaeSession.kindName).filter("lastseen <", time()-GaeSession.lifeTime ).run(limit=1000,keysOnly=True)


current = SessionWrapper( GaeSession )
