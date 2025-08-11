import datetime
import logging
import time
import typing as t

from viur.core import current, db, tasks, utils
from viur.core.config import conf  # this import has to stay alone due partial import
from viur.core.tasks import DeleteEntitiesIter

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

_SENTINEL: t.Final[object] = object()

TObserver = t.TypeVar("TObserver", bound=t.Callable[[db.Entity], None])
"""Type of the observer for :meth:`Session.on_delete`"""


class Session(db.Entity):
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
    use_session_cookie = False  # If True, issue the cookie without a lifeTime (will disappear on browser close)
    cookie_name = f"""viur_cookie_{conf.instance.project_id}"""
    GUEST_USER = "__guest__"

    _ON_DELETE_OBSERVER = []

    def __init__(self):
        super().__init__()
        self.changed = False
        self.cookie_key = None
        self.static_security_key = None
        self.loaded = False

    def load(self):
        """
            Initializes the Session.

            If the client supplied a valid Cookie, the session is read from the datastore, otherwise a new,
            empty session will be initialized.
        """

        if cookie_key := current.request.get().request.cookies.get(self.cookie_name):
            cookie_key = str(cookie_key)
            if data := db.get(db.Key(self.kindName, cookie_key)):  # Loaded successfully
                if data["lastseen"] < time.time() - conf.user.session_life_time.total_seconds():
                    # This session is too old
                    self.reset()
                    return False

                self.loaded = True
                self.cookie_key = cookie_key

                super().clear()
                super().update(data["data"])

                self.static_security_key = data.get("static_security_key") or data.get("staticSecurityKey")
                if data["lastseen"] < time.time() - 5 * 60:  # Refresh every 5 Minutes
                    self.changed = True

            else:
                self.reset()

    def save(self):
        """
            Writes the session into the database.

            Does nothing, in case the session hasn't been changed in the current request.
        """

        if not self.changed:
            return
        current_request = current.request.get()
        # We will not issue sessions over http anymore
        if not (current_request.isSSLConnection or conf.instance.is_dev_server):
            return

        # Get the current user's key
        try:
            # Check for our custom user-api
            user_key = conf.main_app.vi.user.getCurrentUser()["key"]
        except Exception:
            user_key = Session.GUEST_USER  # this is a guest

        if not self.loaded:
            self.cookie_key = utils.string.random(42)
            self.static_security_key = utils.string.random(13)

        dbSession = db.Entity(db.Key(self.kindName, self.cookie_key))

        dbSession["data"] = db.fix_unindexable_properties(self)
        dbSession["static_security_key"] = self.static_security_key
        dbSession["lastseen"] = time.time()
        dbSession["user"] = str(user_key)  # allow filtering for users
        dbSession.exclude_from_indexes = {"data"}

        db.put(dbSession)

        # Provide Set-Cookie header entry with configured properties
        flags = (
            "Path=/",
            "HttpOnly",
            f"SameSite={self.same_site}" if self.same_site and not conf.instance.is_dev_server else None,
            "Secure" if not conf.instance.is_dev_server else None,
            f"Max-Age={int(conf.user.session_life_time.total_seconds())}" if not self.use_session_cookie else None,
        )

        current_request.response.headerlist.append(
            ("Set-Cookie", f"{self.cookie_name}={self.cookie_key};{';'.join([f for f in flags if f])}")
        )

    def __setitem__(self, key: str, item: t.Any):
        """
            Stores a new value under the given key.

            If that key exists before, its value is
            overwritten.
        """
        super().__setitem__(key, item)
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

        self.clear()
        self.cookie_key = utils.string.random(42)
        self.static_security_key = utils.string.random(13)
        self.loaded = True
        self.changed = True

    def __delitem__(self, key: str) -> None:
        """
            Removes a *key* from the session.
            This key must exist.
        """
        super().__delitem__(key)
        self.changed = True

    def __ior__(self, other: dict) -> t.Self:
        """
        Merges the contents of a dict into the session.
        """
        super().__ior__(other)
        self.changed = True
        return self

    def update(self, other: dict) -> None:
        """
        Merges the contents of a dict into the session.
        """
        self |= other

    def pop(self, key: str, default=_SENTINEL) -> t.Any:
        """
        Delete a specified key from the session.

        If key is in the session, remove it and return its value, else return default.
        If default is not given and key is not in the session, a KeyError is raised.
        """
        if key in self or default is _SENTINEL:
            value = super().pop(key)
            self.changed = True

            return value

        return default

    def clear(self) -> None:
        if self.cookie_key:
            db.delete(db.Key(self.kindName, self.cookie_key))
            from viur.core import securitykey
            securitykey.clear_session_skeys(self.cookie_key)

        current.request.get().response.unset_cookie(self.cookie_name, strict=False)

        self.loaded = False
        self.cookie_key = None
        super().clear()

    def popitem(self) -> t.Tuple[t.Any, t.Any]:
        self.changed = True
        return super().popitem()

    def setdefault(self, key, default=None) -> t.Any:
        if key not in self:
            self.changed = True
        return super().setdefault(key, default)

    @classmethod
    def on_delete(cls, func: TObserver, /) -> TObserver:
        """Decorator to register an observer for the _session delete event_."""
        cls._ON_DELETE_OBSERVER.append(func)
        return func

    @classmethod
    def dispatch_on_delete(cls, entry: db.Entity) -> None:
        """Call the observers for the _session delete event_."""
        for observer in cls._ON_DELETE_OBSERVER:
            observer(entry)


class DeleteSessionsIter(DeleteEntitiesIter):
    """
    QueryIter to delete all session entities encountered.

    Each deleted entity triggers a _session delete event_
    which is dispatched by :meth:`Session.dispatch_on_delete`.
    """

    @classmethod
    def handleEntry(cls, entry: db.Entity, customData: t.Any) -> None:
        db.delete(entry.key)
        Session.dispatch_on_delete(entry)


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
    DeleteSessionsIter.startIterOnQuery(query)


@tasks.PeriodicTask(interval=datetime.timedelta(hours=4))
def start_clear_sessions():
    """
        Removes old (expired) Sessions
    """
    query = db.Query(Session.kindName).filter(
        "lastseen <", time.time() - (conf.user.session_life_time.total_seconds() + 300))
    DeleteSessionsIter.startIterOnQuery(query)
