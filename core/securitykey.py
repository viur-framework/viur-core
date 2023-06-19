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
import typing
import datetime
from viur.core import conf, utils, current, db, tasks
from viur.core.tasks import DeleteEntitiesIter

SECURITYKEY_KINDNAME = "viur-securitykey"
SECURITYKEY_DURATION = 24 * 60 * 60  # one day


def create(duration: typing.Union[None, int] = None, session: bool = True, **custom_data) -> str:
    """
        Creates a new one-time security key or returns a valid CSRF-token for the current session.

        The custom data (given as **custom_data) that can be stored with the key.
        Any data provided must be serializable by the datastore.

        :param duration: Make this key valid for a fixed timeframe of seconds
        :param session: Bind this key to the current session
        :param custom_data: Any other data is stored behind the skey.

        :returns: The new one-time key, which is a randomized string.
    """
    if any(k.startswith("viur_") for k in custom_data):
        raise ValueError("custom_data keys with a 'viur_'-prefix are reserved.")

    if not duration:
        duration = conf["viur.session.lifeTime"] if session else SECURITYKEY_DURATION

    key = utils.generateRandomString()

    entity = db.Entity(db.Key(SECURITYKEY_KINDNAME, key))
    entity |= custom_data

    entity["viur_session"] = current.session.get().cookie_key if session else None
    entity["viur_until"] = utils.utcNow() + datetime.timedelta(seconds=int(duration))
    db.Put(entity)

    return key


def validate(key: str, session: bool = True) -> typing.Union[bool, db.Entity]:
    """
        Validates a security key.

        :param key: The key to be validated.
        :param session: If True, validate against a session's skey, otherwise lookup an unbound key
        :returns: False if the key was not valid for whatever reasons, the data (given during :meth:`create`) as
            dictionary or True if the dict is empty (or session was True).
    """
    if session and key == "staticSessionKey":
        skey_header_value = current.request.get().request.headers.get("Sec-X-ViUR-StaticSKey")
        if skey_header_value and current.session.get().validateStaticSecurityKey(skey_header_value):
            return True

        return False

    if not key or not (entity := db.Get(db.Key(SECURITYKEY_KINDNAME, key))):
        return False

    # First of all, delete the entity, validation is done afterward.
    db.Delete(entity)

    # Key has expired?
    if entity["viur_until"] < utils.utcNow():
        return False

    del entity["viur_until"]

    # Key is session bound?
    if session:
        if entity["viur_session"] != current.session.get().cookie_key:
            return False
    elif entity["viur_session"]:
        return False

    del entity["viur_session"]

    return entity or True


@tasks.PeriodicTask(60 * 4)
def periodic_clear_skeys():
    """
        Removes old (expired) skeys
    """
    query = db.Query(SECURITYKEY_KINDNAME).filter("viur_until <", utils.utcNow() - datetime.timedelta(seconds=300))
    DeleteEntitiesIter.startIterOnQuery(query)


@tasks.CallDeferred
def clear_session_skeys(session_key):
    """
        Removes any skeys bound to a specific session.
    """
    query = db.Query(SECURITYKEY_KINDNAME).filter("viur_session", session_key)
    DeleteEntitiesIter.startIterOnQuery(query)
