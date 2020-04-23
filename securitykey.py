# -*- coding: utf-8 -*-

"""
	This module provides onetime keys. Such a Securitykey can only be used once to authenticate an action like
	edit an entry. Unless specified otherwise, keys are bound to a session. This prevents such actions from beeing
	executed without explicit user consent so an attacker can't send special crafted links (like /user/delete/xxx)
	to a authenticated user as these links would lack a valid securityKey.

	Its also possible to store data along with a securityKey and specify a lifeTime.

"""

from datetime import datetime, timedelta
from viur.core.utils import generateRandomString
from viur.core.utils import currentSession, currentRequest
from viur.core import request
from viur.core import db, conf
from viur.core.tasks import PeriodicTask, callDeferred
from typing import Union

securityKeyKindName = "viur-securitykeys"


def create(duration: Union[None, int] = None, **kwargs):
	"""
		Creates a new onetime Securitykey for the current session
		If duration is not set, this key is valid only for the current session.
		Otherwise, the key and its data is serialized and saved inside the datastore
		for up to duration-seconds

		:param duration: Make this key valid for a fixed timeframe (and independend of the current session)
		:type duration: int or None
		:returns: The new onetime key
	"""
	if not duration:
		return currentSession.get().getSecurityKey()
	key = generateRandomString()
	duration = int(duration)
	dbObj = db.Entity(securityKeyKindName, name=key)
	for k, v in kwargs.items():
		dbObj[k] = v
	dbObj["until"] = datetime.now() + timedelta(seconds=duration)
	db.Put(dbObj)
	return key


def validate(key: str, useSessionKey: bool) -> Union[bool, db.Entity]:
	"""
		Validates a onetime securitykey

		:type key: str
		:param key: The key to validate
		:type useSessionKey: Bool
		:param useSessionKey: If True, we validate against the session's skey, otherwise we'll lookup an unbound key
		:returns: False if the key was not valid for whatever reasons, the data (given during createSecurityKey) as dictionary or True if the dict is empty.
	"""
	if useSessionKey:
		if key == "staticSessionKey":
			skeyHeaderValue = currentRequest.get().request.headers.get("Sec-X-ViUR-StaticSKey")
			if skeyHeaderValue and currentSession.get().validateStaticSecurityKey(skeyHeaderValue):
				return True
		elif currentSession.get().validateSecurityKey(key):
			return True
		return False
	if not key:
		return False
	dbKey = db.Key(securityKeyKindName, key)
	dbObj = db.Get(dbKey)
	if dbObj:
		db.Delete(dbKey)
		if dbObj["until"] < datetime.now():  # This key has expired
			return False
		del dbObj["until"]
		if not dbObj:
			return True
		return dbObj
	return False


@PeriodicTask(60 * 4)
def startClearSKeys():
	"""
		Removes old (expired) skeys
	"""
	doClearSKeys((datetime.now() - timedelta(seconds=300)).strftime("%d.%m.%Y %H:%M:%S"), None)


@callDeferred
def doClearSKeys(timeStamp, cursor):
	gotAtLeastOne = False
	query = db.Query(securityKeyKindName).filter("until <", datetime.strptime(timeStamp, "%d.%m.%Y %H:%M:%S"))
	for oldKey in query.run(100, keysOnly=True):
		gotAtLeastOne = True
		db.Delete(oldKey)
	newCursor = query.getCursor()
	if gotAtLeastOne and newCursor and newCursor.urlsafe() != cursor:
		doClearSKeys(timeStamp, newCursor.urlsafe())
