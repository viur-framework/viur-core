# -*- coding: utf-8 -*-

"""
	This module provides onetime keys. Such a Securitykey can only be used once to authenticate an action like
	edit an entry. Unless specified otherwise, keys are bound to a session. This prevents such actions from beeing
	executed without explicit user consent so an attacker can't send special crafted links (like /user/delete/xxx)
	to a authenticated user as these links would lack a valid securityKey.

	Its also possible to store data along with a securityKey and specify a lifeTime.

"""


from datetime import datetime, timedelta
from server.utils import generateRandomString
from server.session import current as currentSession
from server import db, conf
from server.tasks import PeriodicTask, callDeferred


securityKeyKindName = "viur-securitykeys"

def create( duration=None, **kwargs ):
	"""
		Creates a new onetime Securitykey for the current session
		If duration is not set, this key is valid only for the current session.
		Otherwise, the key and its data is serialized and saved inside the datastore
		for up to duration-seconds

		:param duration: Make this key valid for a fixed timeframe (and independend of the current session)
		:type duration: int or None
		:returns: The new onetime key
	"""
	key = generateRandomString()
	if duration is None:
		sessionDependend = True
		duration = 30*60 # 30 Mins from now
	else:
		sessionDependend = False
		duration = int( duration )
	dbObj = db.Entity(securityKeyKindName, name=key )
	for k, v in kwargs.items():
		dbObj[ k ] = v
	dbObj["until"] = datetime.now()+timedelta( seconds=duration )
	if sessionDependend:
		dbObj["session"] = currentSession.getSessionKey()
	else:
		dbObj["session"] = None
	dbObj.set_unindexed_properties( [x for x in dbObj.keys() if not x=="until" ] )
	db.Put( dbObj )
	return( key )

def validate( key, acceptSessionKey=False ):
	"""
		Validates a onetime securitykey

		:type key: str
		:param key: The key to validate
		:type acceptSessionKey: Bool
		:param acceptSessionKey: If True, we also accept the session's skey
		:returns: False if the key was not valid for whatever reasons, the data (given during createSecurityKey) as dictionary or True if the dict is empty.
	"""
	if acceptSessionKey:
		if key==currentSession.getSessionSecurityKey():
			return( True )
	try:
		dbObj = db.Get( db.Key.from_path( securityKeyKindName, key ) )
	except:
		return( False )
	if dbObj:
		if "session" in dbObj and dbObj["session"] is not None:
			if dbObj["session"] != currentSession.getSessionKey():
				return( False )
		db.Delete( dbObj.key() )
		if dbObj[ "until" ] < datetime.now(): #This key has expired
			return( False )
		res ={}
		for k in dbObj.keys():
			res[ k ] = dbObj[ k ]
		del res["session"]
		del res["until"]
		if not res:
			return( True )
		return( res )
	return( False )

@PeriodicTask(60*4)
def startClearSKeys():
	"""
		Removes old (expired) skeys
	"""
	doClearSKeys( (datetime.now()-timedelta(seconds=300)).strftime("%d.%m.%Y %H:%M:%S"), None )

@callDeferred
def doClearSKeys( timeStamp, cursor ):
	gotAtLeastOne = False
	query = db.Query( securityKeyKindName ).filter( "until <", datetime.strptime(timeStamp,"%d.%m.%Y %H:%M:%S") )
	for oldKey in query.run(100, keysOnly=True):
		gotAtLeastOne = True
		db.Delete( oldKey )
	newCursor = query.getCursor()
	if gotAtLeastOne and newCursor and newCursor.urlsafe()!=cursor:
		doClearSKeys( timeStamp, newCursor.urlsafe() )

