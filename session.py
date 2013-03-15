# -*- coding: utf-8 -*-
import threading
from google.appengine.ext import db
from google.appengine.api import memcache
import json
import string, random
from time import time
from server.tasks import PeriodicTask
from google.appengine.runtime.apiproxy_errors import CapabilityDisabledError, OverQuotaError

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
	
	def load( self, coockie ):
		if not "session" in dir( self ):
			self.session = self.factory()
		if coockie and self.cookieName in coockie.keys():
			return( self.session.load( coockie[ self.cookieName ] ) )
		return( self.session.load( None ) )
	
	def __contains__( self, key ):
		try:
			return( key in self.session.keys() ) 
		except AttributeError:
			return( False )
	
	def __delitem__(self, key ):
		del self.session[key]
	
	def __getitem__( self, key ):
		try:
			return( self.session[ key ] )
		except AttributeError:
			return( None )

	def get( self, key ):#fixme
		"""For compatibility with cherrypy"""
		try:
			return( self.session.get( key ) )
		except AttributeError:
			return( None )
		
	def __setitem__( self, key, item ):
		try:
			self.session[ key ] = item
		except AttributeError:
			pass
	
	def save(self):
		try:
			return( self.session.save())
		except AttributeError:
			return( None )
	
	def markChanged(self):
		try:
			self.session.markChanged()
		except AttributeError:
			pass
	
	def forceInitializion(self):
		try:
			return( self.session.forceInitializion() )
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
	class SessionData( db.Expando ):
		pass

	"""Store Sessions inside the Big Table/Memcache"""
	def load( self, cookie=None ):
		self.changed = False
		self.key = None
		self.session = {}
		if cookie:
			data = None #memcache.get( "session-"+str(cookie).strip("\"") )
			if data: #Loaded successfully from Memcache
				try:
					lastseen, self.session = data
					if lastseen < time()-5*60: #Refresh every 5 Minutes
						self.changed = True
				except:
					self.session = {}
			if not self.session: #Load from Memcache failed
				try:
					data = GaeSession.SessionData.get_by_key_name( str(cookie).strip("\"") )
				except OverQuotaError, CapabilityDisabledError:
					data = None
				if data:
					self.session = json.loads( data.data )
					if isinstance( self.session, list ): #We seem to have a bug here...
						self.session = {}
					try:
						if not "lastseen" in data.dynamic_properties() or data.lastseen<time()-5*60:
							"""Ensure the session gets updated at least each 5 minutes"""
							self.changed = True
					except:
						pass
			if self.session:
				self.key = str( cookie )
				return( True )
			else:
				self.session = {}
				return( False )
	
	def save(self):
		if self.session and self.changed:
			if not self.key:
				self.key = ''.join(random.choice(string.ascii_lowercase+string.ascii_uppercase + string.digits) for x in range(42))
			try:
				dbSession = GaeSession.SessionData( key_name=self.key )
				dbSession.data = db.Text( json.dumps( self.session ) )
				dbSession.lastseen = time()
				dbSession.put()
			except OverQuotaError, CapabilityDisabledError:
				pass
			#memcache.set( "session-"+self.key, (time(), self.session), self.lifeTime)
			return( str(self.key) )
		else:
			if self.key:
				return( self.key )
			return( None )

	def __contains__( self, key ):
		return( key in self.session ) 
	
	def __delitem__(self, key ):
		del self.session[key]
		self.changed = True
	
	def __getitem__( self, key ):
		return( self.session[ key ] )
	
	def get( self, key ): 
		if( key in self.session.keys() ):
			return( self.session[ key ] )
		else:
			return( None )
		
	def __setitem__( self, key, item ):
		self.session[ key ] = item
		self.changed = True
	
	def markChanged(self):
		self.changed = True
		
	def forceInitializion(self):
		if not self.key:
			self.key = ''.join(random.choice(string.ascii_lowercase+string.ascii_uppercase + string.digits) for x in range(42))
			self.session["_forceInit"] = True
			self.changed = True
		return( self.key )
	
@PeriodicTask( 60 )
def cleanup( ):
	oldSessions = GaeSession.SessionData.all().filter("lastseen <", time()-GaeSession.lifeTime ).fetch(1000)
	while( oldSessions ):
		db.delete( oldSessions )
		oldSessions = GaeSession.SessionData.all().filter("lastseen <", time()-GaeSession.lifeTime ).fetch(1000)


current = SessionWrapper( GaeSession )
