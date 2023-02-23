"""
    This module provides one-time keys.

    There are two types of security keys:

    1. If :meth:create is called without arguments, it returns the current session CSRF token. Repeated calls to
        :meth:create will return the same CSRF token (for the same session) until that token has been redeemed.
        This security key will be valid as long the session is active, and it's not possible to store data along with
        that key. These are usually used as a CSRF token.
        This has been changed from ViUR2 - where it was possible to create a arbitrary number of security keys per
        session.
    2. If :meth:create is called with a duration (and optional kwargs values), it will create a security key
        that is *not* bound to the current session, but it's possible to store custom data (provided by kwargs).
        As these are not bound to the session, each call to :meth:create will yield a new token.
        These are used if it's expected that the token may be redeemed on a different device (e.g. when sending an
        email address confirmation)

    ..note:
        There's also a hidden 3rd type of security-key: The sessions static security key.

        This key is only revealed once (during login, as the protected header Sec-X-ViUR-StaticSKey).

        This can be used instead of the one-time sessions security key by sending it back as the same protected HTTP
        header and setting the skey value to "staticSessionKey". This is only intended for non-web-browser,
        programmatic access (admin tools, import tools etc.) where CSRF attacks are not applicable.

        Therefor that header is prefixed with "Sec-" - so it cannot be read or set using JavaScript.
"""
from viur.core import utils, current, db, tasks
from datetime import datetime, timedelta
from typing import Union

SECURITYKEY_KINDNAME = "viur-securitykeys"


def create(duration: Union[None, int] = None, **custom_data) -> str:
    """
        Creates a new onetime Securitykey or returns the current sessions csrf-token.
        The custom data (given as keyword arguments) that can be stored with the key if :param:duration is set must
        be serializable by the datastore.

        :param duration: Make this key valid for a fixed timeframe (and independent of the current session)
        :returns: The new onetime key
    """
    if not duration:
        if custom_data:
            raise ValueError("kwargs are not allowed when session security key is wanted")

        return current.session.get().getSecurityKey()

    key = utils.generateRandomString()
    duration = int(duration)

    entity = db.Entity(db.Key(SECURITYKEY_KINDNAME, key))
    entity |= custom_data

    entity["until"] = utils.utcNow() + timedelta(seconds=duration)
    db.Put(entity)

    return key


def validate(key: str, useSessionKey: bool) -> Union[bool, db.Entity]:
    """
        Validates a security key.

        If useSessionKey is True, the key is expected to be the session's current security key
        or its static security key.
        Otherwise, it must be a key created with a duration, so that it is session independent.

        :param key: The key to be validated
        :param useSessionKey: If True, validate against the session's skey, otherwise lookup an unbound key
        :returns: False if the key was not valid for whatever reasons, the data (given during createSecurityKey) as
            dictionary or True if the dict is empty (or useSessionKey was True).
    """
    if useSessionKey:
        session = current.session.get()
        if key == "staticSessionKey":
            request = current.request.get()
            skey_header_value = request.request.headers.get("Sec-X-ViUR-StaticSKey")
            if skey_header_value and session.validateStaticSecurityKey(skey_header_value):
                return True

        elif session.validateSecurityKey(key):
            return True

        return False

    if not key or not (entity := db.Get(db.Key(SECURITYKEY_KINDNAME, key))):
        return False

    db.Delete(entity)

    # Key has expired?
    if entity["until"] < utils.utcNow():
        return False

    del entity["until"]

    return entity or True


@tasks.PeriodicTask(60 * 4)
def start_clear_skeys():
    """
        Removes old (expired) skeys
    """
    do_clear_skeys(datetime.now() - timedelta(seconds=300))


@tasks.CallDeferred
def do_clear_skeys(until: datetime):
    query = db.Query(SECURITYKEY_KINDNAME).filter("until <", until)

    for oldKey in query.run(100):
        db.Delete(oldKey)

    if query.getCursor():
        do_clear_skeys(until)
