"""
    This module provides onetime keys.
    There are two types of security keys:
    - If :meth:create is called without arguments, it returns the current session CSRF token. Repeated calls to
        :meth:create will return the same CSRF token (for the same session) until that token has been redeemed.
        This security key will be valid as long the session is active and it's not possible to store data along with
        that key. These are usually used as a CSRF token.
        This has been changed from ViUR2 - where it was possible to create a arbitrary number of security keys per
        session.
    - If :meth:create is called with a duration (and optional keyword-parameters), it will create a security key
        that is *not* bound to the current session, but it's possible to store custom data (the excess keyword
        arguments passed to :meth:create). As these are not bound to the session, each call to :meth:create will yield
        a new token. These are used if it's expected that the token may be redeemed on a different device (eg. when
        sending an email address confirmation email)

    ..note: There's a hidden 3rd type of security-key: The sessions static security key. This key is only revealed once
        (during login, as the protected header Sec-X-ViUR-StaticSKey). This can be used instead of the onetime sessions
        security key by sending it back as the same protected http header and setting the skey value to
        "staticSessionKey". This is only intended for non-webbrowser, programmatic access
        (ViUR Admin, import tools etc) where CSRF attacks are not applicable. Therefore that header is prefixed with
        "Sec-" - so it cannot be read or set by javascript.
"""
from datetime import datetime, timedelta
from viur.core.utils import generateRandomString
from viur.core.utils import currentSession, currentRequest
from viur.core import db
from viur.core.tasks import PeriodicTask, CallDeferred
from typing import Union
from viur.core.utils import utcNow

securityKeyKindName = "viur-securitykeys"


def create(duration: Union[None, int] = None, **kwargs) -> str:
    """
        Creates a new onetime Securitykey or returns the current sessions csrf-token.
        The custom data (given as keyword arguments) that can be stored with the key if :param:duration is set must
        be serializable by the datastore.

        :param duration: Make this key valid for a fixed timeframe (and independent of the current session)
        :returns: The new onetime key
    """
    if not duration:
        assert not kwargs, "kwargs are not allowed when session security key is wanted"
        return currentSession.get().getSecurityKey()
    key = generateRandomString()
    duration = int(duration)
    dbObj = db.Entity(db.Key(securityKeyKindName, key))
    for k, v in kwargs.items():
        dbObj[k] = v
    dbObj["until"] = utcNow() + timedelta(seconds=duration)
    db.Put(dbObj)
    return key


def validate(key: str, useSessionKey: bool) -> Union[bool, db.Entity]:
    """
        Validates a security key. If useSessionKey is true, the key is expected to be the sessions current security key
        (or it's static security key). Otherwise it must be a key created with a duration (so it's not session
        dependent)

        :param key: The key to validate
        :param useSessionKey: If True, we validate against the session's skey, otherwise we'll lookup an unbound key
        :returns: False if the key was not valid for whatever reasons, the data (given during createSecurityKey) as
            dictionary or True if the dict is empty (or :param:useSessionKey was true).
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
        until = dbObj["until"]
        if until < utcNow():  # This key has expired
            return False
        del dbObj["until"]
        if not dbObj:
            return True
        return dbObj
    return False


@PeriodicTask(60 * 4)
def startClearSKeys() -> None:
    """
        Removes old (expired) skeys
    """
    doClearSKeys((datetime.now() - timedelta(seconds=300)).strftime("%d.%m.%Y %H:%M:%S"))


@CallDeferred
def doClearSKeys(timeStamp: str) -> None:
    query = db.Query(securityKeyKindName).filter("until <", datetime.strptime(timeStamp, "%d.%m.%Y %H:%M:%S"))
    for oldKey in query.run(100):
        db.Delete(oldKey)
    if query.getCursor():
        doClearSKeys(timeStamp)
