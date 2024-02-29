"""
    Implementation of one-time CSRF-security-keys.

    CSRF-security-keys (Cross-Site Request Forgery) are used mostly to make requests unique and non-reproducible.
    Doing the same request again requires to obtain a fresh security key first.
    Furthermore, security keys can be used to implemented credential-reset mechanisms or similar features, where a
    URL is only valid for one call.

    ..note:
        There's also a hidden 3rd type of security-key: The session's static security key.

        This key is only revealed once during login, as the protected header "Sec-X-ViUR-StaticSessionKey".

        This can be used instead of the one-time sessions security key by sending it back as the same protected HTTP
        header and setting the skey value to "STATIC_SESSION_KEY". This is only intended for non-web-browser,
        programmatic access (admin tools, import tools etc.) where CSRF attacks are not applicable.

        Therefor that header is prefixed with "Sec-" - so it cannot be read or set using JavaScript.
"""
import typing as t
import datetime
import hmac
from viur.core import conf, utils, current, db, tasks

SECURITYKEY_KINDNAME = "viur-securitykey"
SECURITYKEY_DURATION = 24 * 60 * 60  # one day
SECURITYKEY_STATIC_HEADER: t.Final[str] = "Sec-X-ViUR-StaticSessionKey"
"""The name of the header in which the static session key is provided at login
and must be specified in requests that require a skey."""
SECURITYKEY_STATIC_SKEY: t.Final[str] = "STATIC_SESSION_KEY"
"""Value that must be used as a marker in the payload (key: skey) to indicate
that the session key from the headers should be used."""


def create(
        duration: None | int | datetime.timedelta = None,
        session_bound: bool = True,
        key_length: int = 13,
        indexed: bool = True,
        **custom_data) -> str:
    """
        Creates a new one-time CSRF-security-key.

        The custom data (given as **custom_data) that can be stored with the key.
        Any data provided must be serializable by the datastore.

        :param duration: Make this CSRF-token valid for a fixed timeframe.
        :param session_bound: Bind this CSRF-token to the current session.
        :param indexed: Indexes all values stored with the security-key (default), set False to not index.
        :param custom_data: Any other data is stored with the CSRF-token, for later re-use.

        :returns: The new one-time key, which is a randomized string.
    """
    if any(k.startswith("viur_") for k in custom_data):
        raise ValueError("custom_data keys with a 'viur_'-prefix are reserved.")

    if not duration:
        duration = conf.user.session_life_time if session_bound else SECURITYKEY_DURATION
    key = utils.string.random(key_length)

    entity = db.Entity(db.Key(SECURITYKEY_KINDNAME, key))
    entity |= custom_data

    entity["viur_session"] = current.session.get().cookie_key if session_bound else None
    entity["viur_until"] = utils.utcNow() + utils.parse.timedelta(duration)


    if not indexed:
        entity.exclude_from_indexes = [k for k in entity.keys() if not k.startswith("viur_")]

    db.Put(entity)

    return key


def validate(key: str, session_bound: bool = True) -> bool | db.Entity:
    """
        Validates a CSRF-security-key.

        :param key: The CSRF-token to be validated.
        :param session_bound: If True, make sure the CSRF-token is created inside the current session.
        :returns: False if the key was not valid for whatever reasons, the data (given during :meth:`create`) as
            dictionary or True if the dict is empty (or session was True).
    """
    if session_bound and key == SECURITYKEY_STATIC_SKEY:
        if skey_header_value := current.request.get().request.headers.get(SECURITYKEY_STATIC_HEADER):
            return hmac.compare_digest(current.session.get().static_security_key, skey_header_value)

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
    if session_bound:
        if entity["viur_session"] != current.session.get().cookie_key:
            return False
    elif entity["viur_session"]:
        return False

    del entity["viur_session"]

    return entity or True


@tasks.PeriodicTask(60 * 4)
def periodic_clear_skeys():
    from viur.core import tasks
    """
        Removes expired CSRF-security-keys periodically.
    """
    query = db.Query(SECURITYKEY_KINDNAME).filter("viur_until <", utils.utcNow() - datetime.timedelta(seconds=300))
    tasks.DeleteEntitiesIter.startIterOnQuery(query)


@tasks.CallDeferred
def clear_session_skeys(session_key):
    from viur.core import tasks
    """
        Removes any CSRF-security-keys bound to a specific session.
        This function is called by the Session-module based on reset-actions.
    """
    query = db.Query(SECURITYKEY_KINDNAME).filter("viur_session", session_key)
    tasks.DeleteEntitiesIter.startIterOnQuery(query)
