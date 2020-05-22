# -*- coding: utf-8 -*-
from time import time
from viur.core.tasks import PeriodicTask, callDeferred
from viur.core import db, utils
from viur.core.config import conf
import logging, pickle
from hmac import compare_digest


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




class GaeSession:
	plainCookieName = "viurHttpCookie"
	sslCookieName = "viurSSLCookie"
	kindName = "viur-session"
	sameSite = "lax"

	"""Store Sessions inside the Big Table/Memcache"""

	def load(self, req):
		"""
			Initializes the Session.

			If the client supplied a valid Cookie, the session is read
			from the memcache/datastore, otherwise a new, empty session
			will be initialized.
		"""
		self.changed = False
		self.isInitial = False
		self.httpKey = None
		self.sslKey = None
		self.staticSecurityKey = None
		self.securityKey = None
		self.session = {}
		if self.plainCookieName in req.request.cookies:
			cookie = str(req.request.cookies[self.plainCookieName])
			data = db.Get(db.Key(self.kindName, cookie))
			if data:  # Loaded successfully from Memcache
				if data["lastseen"] < time() - conf["viur.session.lifeTime"]:
					# This session is too old
					self.reset()
					return False
				self.session = pickle.loads(data["data"])
				self.sslKey = data["sslkey"]
				self.staticSecurityKey = data["staticSecurityKey"]
				self.securityKey = data["securityKey"]
				self.httpKey = cookie
				if data["lastseen"] < time() - 5 * 60:  # Refresh every 5 Minutes
					self.changed = True
			else:
				# We could not load from firebase; create a new one
				self.reset()
			if req.isSSLConnection and self.sslKey and not req.request.cookies.get(self.sslCookieName) == self.sslKey:
				logging.critical("Possible session hijack attempt! Session dropped.")
				self.reset()
				return False
			return True
		else:
			self.reset()

	def save(self, req):
		"""
			Writes the session to the memcache/datastore.

			Does nothing, if the session hasn't been changed in the current request.
		"""
		try:
			if self.changed or self.isInitial:
				# Get the current user id
				try:
					# Check for our custom user-api
					userid = conf["viur.mainApp"].user.getCurrentUser()["key"]
				except:
					userid = None
				if self.isInitial and not req.isSSLConnection:
					# Reset the Secure only key to None - we can't set it anyway.
					self.sslKey = None
				try:
					dbSession = db.Entity(db.Key(self.kindName, self.httpKey))
					dbSession["data"] = pickle.dumps(self.session)
					dbSession["sslkey"] = self.sslKey
					dbSession["staticSecurityKey"] = self.staticSecurityKey
					dbSession["securityKey"] = self.securityKey
					dbSession["lastseen"] = time()
					# Store the userid inside the sessionobj, so we can kill specific sessions if needed
					dbSession["user"] = str(userid) or "guest"
					dbSession.exclude_from_indexes = ["data"]
					db.Put(dbSession)
				except Exception as e:
					logging.exception(e)
					raise  # FIXME
					pass
				if self.sameSite:
					sameSite = "; SameSite=%s" % self.sameSite
				else:
					sameSite = ""
				req.response.headerlist.append(("Set-Cookie", "%s=%s; Max-Age=99999; Path=/; HttpOnly%s" % (
				self.plainCookieName, self.httpKey, sameSite)))
				if req.isSSLConnection:
					req.response.headerlist.append(("Set-Cookie", "%s=%s; Max-Age=99999; Path=/; Secure; HttpOnly%s" % (
					self.sslCookieName, self.sslKey, sameSite)))
		except Exception as e:
			raise  # FIXME
			logging.exception(e)

	def __contains__(self, key):
		"""
			Returns True if the given *key* is set in the current session.
		"""
		return key in self.session

	def __delitem__(self, key):
		"""
			Removes a *key* from the session.

			This key must exist.
		"""
		del self.session[key]
		self.changed = True

	def __getitem__(self, key):
		"""
			Returns the value stored under the given *key*.

			The key must exist.
		"""
		return self.session[key]

	def get(self, key):
		"""
			Returns the value stored under the given key.

			:param key: Key to retrieve from the session variables.
			:type key: str

			:return: Returns None if the key doesn't exist.
		"""
		if key in self.session:
			return self.session[key]
		else:
			return None

	def __setitem__(self, key, item):
		"""
			Stores a new value under the given key.

			If that key exists before, its value is
			overwritten.
		"""
		self.session[key] = item
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
		if self.httpKey:
			db.Delete(db.Key(self.kindName, self.httpKey))
		self.httpKey = utils.generateRandomString(42)
		self.sslKey = utils.generateRandomString(42)
		self.staticSecurityKey = utils.generateRandomString(13)
		self.securityKey = utils.generateRandomString(13)
		self.changed = True
		self.isInitial = True
		self.session = db.Entity()
		if lang:
			self.session["language"] = lang

	def items(self):
		"""
			Returns all items in the current session.
		"""
		return self.session.items()

	def getSecurityKey(self):
		return self.securityKey

	def validateSecurityKey(self, key):
		"""
		Checks if key matches the current CSRF-Token of our session. On success, a new key is generated.
		"""
		if compare_digest(self.securityKey, key):
			self.securityKey = utils.generateRandomString(13)
			self.changed = True
			return True
		return False

	def validateStaticSecurityKey(self, key):
		"""
		Checks if key matches the current *static* CSRF-Token of our session.
		"""
		return compare_digest(self.staticSecurityKey, key)


@callDeferred
def killSessionByUser(user=None):
	"""
		Invalidates all active sessions for the given *user*.

		This means that this user is instantly logged out.
		If no user is given, it tries to invalidate **all** active sessions.

		Use "guest" as to kill all sessions not associated with an user.

		:param user: UserID, "guest" or None.
		:type user: str | None
	"""
	logging.error("Invalidating all sessions for %s" % user)
	query = db.Query(GaeSession.kindName)
	if user is not None:
		query.filter("user =", str(user))
	for key in query.iter(keysOnly=True):
		db.Delete(key)


@PeriodicTask(60 * 4)
def startClearSessions():
	"""
		Removes old (expired) Sessions
	"""
	doClearSessions(time() - (conf["viur.session.lifeTime"] + 300), None)


@callDeferred
def doClearSessions(timeStamp, cursor):
	gotAtLeastOne = False
	query = db.Query(GaeSession.kindName).filter("lastseen <", timeStamp)
	for oldKey in query.run(100, keysOnly=True):
		gotAtLeastOne = True
		db.Delete(oldKey)
	newCursor = query.getCursor()
	if gotAtLeastOne and newCursor and newCursor.urlsafe() != cursor:
		doClearSessions(timeStamp, newCursor.urlsafe())
