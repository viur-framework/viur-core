import hmac
import logging
import time
from viur.core.tasks import DeleteEntitiesIter
from viur.core.config import conf  # this import has to stay alone due partial import
from viur.core import db, utils, tasks
import typing as t

"""
    Provides the session implementation for the Google AppEngine™ based on the datastore.
    To access the current session,  and call current.session.get()

    Example:

    .. code-block:: python

        from viur.core import current
        sessionData = current.session.get()
        sessionData["your_key"] = "your_data"
        data = sessionData["your_key"]

    A get-method is provided for convenience.
    It returns None instead of raising an Exception if the key is not found.
"""


class Session:
    """
        Store Sessions inside the datastore.
        The behaviour of this module can be customized in the following ways:

        - :prop:same_site can be set to None, "none", "lax" or "strict" to influence the same-site tag on the cookies
            we set
        - :prop:use_session_cookie is set to True by default, causing the cookie to be treated as a session cookie
            (it will be deleted on browser close). If set to False, it will be emitted with the life-time in
            conf.user.session_life_time.
        - The config variable conf.user.session_life_time: Determines, how long (in seconds) a session is valid.
            Even if :prop:use_session_cookie is set to True, the session is voided server-side after no request has been
            made within the configured lifetime.
        - The config variables conf.user.session_persistent_fields_on_login and
            conf.user.session_persistent_fields_on_logout lists fields, that may survive a login/logout action.
            For security reasons, we completely destroy a session on login/logout (it will be deleted, a new empty
            database object will be created and a new cookie with a different key is sent to the browser). This causes
            all data currently stored to be lost. Only keys listed in these variables will be copied into the new
            session.
    """
    kindName = "viur-session"
    same_site = "lax"  # Either None (don't issue same_site header), "none", "lax" or "strict"
    use_session_cookie = True  # If True, issue the cookie without a lifeTime (will disappear on browser close)
    cookie_name = f"""viur_cookie_{conf.instance.project_id}"""
    GUEST_USER = "__guest__"

    def __init__(self):
        super().__init__()
        self.changed = False
        self.cookie_key = None
        self.static_security_key = None
        self.session = db.Entity()

    def load(self, req):
        """
            Initializes the Session.

            If the client supplied a valid Cookie, the session is read from the datastore, otherwise a new,
            empty session will be initialized.
        """
        if cookie_key := str(req.request.cookies.get(self.cookie_name)):
            if data := db.Get(db.Key(self.kindName, cookie_key)):  # Loaded successfully
                if data["lastseen"] < time.time() - conf.user.session_life_time:
                    # This session is too old
                    self.reset()
                    return False

                self.cookie_key = cookie_key
                self.session = data["data"]
                self.static_security_key = data.get("static_security_key") or data.get("staticSecurityKey")

                if data["lastseen"] < time.time() - 5 * 60:  # Refresh every 5 Minutes
                    self.changed = True
            else:
                self.reset()
        else:
            self.reset()

    def save(self, req):
        """
            Writes the session into the database.

            Does nothing, in case the session hasn't been changed in the current request.
        """
        if not self.changed:
            return

        # We will not issue sessions over http anymore
        if not (req.isSSLConnection or conf.instance.is_dev_server):
            return

        # Get the current user's key
        try:
            # Check for our custom user-api
            user_key = conf.main_app.vi.user.getCurrentUser()["key"]
        except Exception:
            user_key = Session.GUEST_USER  # this is a guest

        dbSession = db.Entity(db.Key(self.kindName, self.cookie_key))

        dbSession["data"] = db.fixUnindexableProperties(self.session)
        dbSession["static_security_key"] = self.static_security_key
        dbSession["lastseen"] = time.time()
        dbSession["user"] = str(user_key)  # allow filtering for users
        dbSession.exclude_from_indexes = {"data"}

        db.Put(dbSession)

        # Provide Set-Cookie header entry with configured properties
        flags = (
            "Path=/",
            "HttpOnly",
            f"SameSite={self.same_site}" if self.same_site and not conf.instance.is_dev_server else None,
            "Secure" if not conf.instance.is_dev_server else None,
            f"Max-Age={conf.user.session_life_time}" if not self.use_session_cookie else None,
        )

        req.response.headerlist.append(
            ("Set-Cookie", f"{self.cookie_name}={self.cookie_key};{';'.join([f for f in flags if f])}")
        )

    def __contains__(self, key: str) -> bool:
        """
            Returns True if the given *key* is set in the current session.
        """
        return key in self.session

    def __delitem__(self, key: str) -> None:
        """
            Removes a *key* from the session.

            This key must exist.
        """
        del self.session[key]
        self.changed = True

    def __getitem__(self, key) -> t.Any:
        """
            Returns the value stored under the given *key*.

            The key must exist.
        """
        return self.session[key]

    def __ior__(self, other: dict):
        """
        Merges the contents of a dict into the session.
        """
        self.session |= other
        return self

    def get(self, key: str, default: t.Any = None) -> t.Any:
        """
            Returns the value stored under the given key.

            :param key: Key to retrieve from the session variables.
            :param default: Default value to return when key does not exist.
        """
        return self.session.get(key, default)

    def __setitem__(self, key: str, item: t.Any):
        """
            Stores a new value under the given key.

            If that key exists before, its value is
            overwritten.
        """
        self.session[key] = item
        self.changed = True

    def markChanged(self) -> None:
        """
            Explicitly mark the current session as changed.
            This will force save() to write into the datastore,
            even if it believes that this session hasn't changed.
        """
        self.changed = True

    def reset(self) -> None:
        """
            Invalidates the current session and starts a new one.

            This function is especially useful at login, where
            we might need to create an SSL-capable session.

            :warning: Everything is flushed.
        """
        if self.cookie_key:
            db.Delete(db.Key(self.kindName, self.cookie_key))
            from viur.core import securitykey
            securitykey.clear_session_skeys(self.cookie_key)

        self.cookie_key = utils.string.random(42)
        self.static_security_key = utils.string.random(13)
        self.session.clear()
        self.changed = True

    def items(self) -> 'dict_items':
        """
            Returns all items in the current session.
        """
        return self.session.items()


@tasks.CallDeferred
def killSessionByUser(user: t.Optional[t.Union[str, "db.Key", None]] = None):
    """
        Invalidates all active sessions for the given *user*.

        This means that this user is instantly logged out.
        If no user is given, it tries to invalidate **all** active sessions.

        Use "__guest__" to kill all sessions not associated with a user.

        :param user: UserID, "__guest__" or None.
    """
    logging.info(f"Invalidating all sessions for {user=}")

    query = db.Query(Session.kindName).filter("user =", str(user))
    for obj in query.iter():
        db.Delete(obj.key)


@tasks.PeriodicTask(60 * 4)
def start_clear_sessions():
    """
        Removes old (expired) Sessions
    """
    query = db.Query(Session.kindName).filter("lastseen <", time.time() - (conf.user.session_life_time + 300))
    DeleteEntitiesIter.startIterOnQuery(query)
