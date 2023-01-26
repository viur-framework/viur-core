import hmac
import logging
import time
from viur.core.request import BrowseHandler
from viur.core.config import conf  # this import has to stay alone due partial import
from viur.core import db, utils, tasks
from typing import Any, Optional

"""
    Provides the session implementation for the Google AppEngine™ based on the datastore.
    To access the current session, use `utils.currentSession.get()`.

    Example:

    .. code-block:: python

        from viur.core.utils import currentSession
        sessionData = currentSession.get()
        sessionData["your_key"] = "your_data"
        data = sessionData["your_key"]

    A get-method is provided for convenience.
    It returns None instead of raising an Exception if the key is not found.
"""


class Session:
    """
        Store Sessions inside the datastore.
        The behaviour of this module can be customized in the following ways:

        - :prop:sameSite can be set to None, "none", "lax" or "strict" to influence the same-site tag on the cookies
            we set
        - :prop:sessionCookie is set to True by default, causing the cookie to be treated as a session cookie (it will
            be deleted on browser close). If set to False, it will be emitted with the life-time in
            conf["viur.session.lifeTime"].
        - The config variable conf["viur.session.lifeTime"]: Determines, how ling (in Minutes) a session stays valid.
            Even if :prop:sessionCookie is set to True, we'll void a session server-side after no request has been made
            within said lifeTime.
        - The config variables conf["viur.session.persistentFieldsOnLogin"] and
            conf["viur.session.persistentFieldsOnLogout"] lists fields, that may survive a login/logout action.
            For security reasons, we completely destroy a session on login/logout (it will be deleted, a new empty
            database object will be created and a new cookie with a different key is sent to the browser). This causes
            all data currently stored to be lost. Only keys listed in these variables will be copied into the new
            session.

    """
    kindName = "viur-session"
    sameSite = "lax"  # Either None (don't issue sameSite header), "none", "lax" or "strict"
    sessionCookie = True  # If True, issue the cookie without a lifeTime (will disappear on browser close)
    cookieName = f'viur_cookie_{conf["viur.instance.project_id"]}'

    def __init__(self):
        super().__init__()
        self.changed = False
        self.isInitial = False
        self.cookieKey = None
        self.sslKey = None
        self.staticSecurityKey = None
        self.securityKey = None
        self.session = {}

    def load(self, req: BrowseHandler):
        """
            Initializes the Session.

            If the client supplied a valid Cookie, the session is read from the datastore, otherwise a new,
            empty session will be initialized.
        """
        if self.cookieName in req.request.cookies:
            cookie = str(req.request.cookies[self.cookieName])
            if data := db.Get(db.Key(self.kindName, cookie)):  # Loaded successfully
                if data["lastseen"] < time.time() - conf["viur.session.lifeTime"]:
                    # This session is too old
                    self.reset()
                    return False

                self.session = data["data"]
                self.staticSecurityKey = data["staticSecurityKey"]
                self.securityKey = data["securityKey"]
                self.cookieKey = cookie

                if data["lastseen"] < time.time() - 5 * 60:  # Refresh every 5 Minutes
                    self.changed = True
            else:
                self.reset()
        else:
            self.reset()

    def save(self, req: BrowseHandler):
        """
            Writes the session to the datastore.

            Does nothing, if the session hasn't been changed in the current request.
        """
        try:
            if self.changed or self.isInitial:
                # We will not issue sessions over http anymore
                if not (req.isSSLConnection or conf["viur.instance.is_dev_server"]):
                    return False

                # Get the current user id
                try:
                    # Check for our custom user-api
                    userid = conf["viur.mainApp"].user.getCurrentUser()["key"]
                except:
                    userid = None

                try:
                    dbSession = db.Entity(db.Key(self.kindName, self.cookieKey))
                    dbSession["data"] = db.fixUnindexableProperties(self.session)
                    dbSession["staticSecurityKey"] = self.staticSecurityKey
                    dbSession["securityKey"] = self.securityKey
                    dbSession["lastseen"] = time.time()
                    dbSession["user"] = str(userid) if userid else None  # to allow filtering for specific users
                    dbSession["guest"] = userid is None  # to allow filtering guest sessions
                    dbSession.exclude_from_indexes = ["data"]
                    db.Put(dbSession)
                except Exception as e:
                    logging.exception(e)
                    raise  # FIXME???

                sameSite = "; SameSite=%s" % self.sameSite if self.sameSite else ""
                secure = "; Secure" if not conf["viur.instance.is_dev_server"] else ""
                maxAge = "; Max-Age=%s" % conf["viur.session.lifeTime"] if not self.sessionCookie else ""
                req.response.headerlist.append(("Set-Cookie", "%s=%s; Path=/; HttpOnly%s%s%s" % (
                    self.cookieName, self.cookieKey, sameSite, secure, maxAge)))

        except Exception as e:
            logging.exception(e)
            raise  # FIXME???

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

    def __getitem__(self, key) -> Any:
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

    def get(self, key: str, default: Any = None) -> Any:
        """
            Returns the value stored under the given key.

            :param key: Key to retrieve from the session variables.
            :param default: Default value to return when key does not exist.
        """
        return self.session.get(key, default)

    def __setitem__(self, key: str, item: Any):
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
        if self.cookieKey:
            db.Delete(db.Key(self.kindName, self.cookieKey))

        self.cookieKey = utils.generateRandomString(42)
        self.staticSecurityKey = utils.generateRandomString(13)
        self.securityKey = utils.generateRandomString(13)
        self.changed = True
        self.isInitial = True
        self.session = db.Entity()

    def items(self) -> 'dict_items':
        """
            Returns all items in the current session.
        """
        return self.session.items()

    def getSecurityKey(self) -> Optional[str]:
        return self.securityKey

    def validateSecurityKey(self, key: str) -> bool:
        """
        Checks if key matches the current CSRF-Token of our session. On success, a new key is generated.
        """
        if hmac.compare_digest(self.securityKey, key):
            # It looks good so far, check if we can acquire that skey inside a transaction
            def exchangeSecurityKey():
                dbSession = db.Get(db.Key(self.kindName, self.cookieKey))
                if not dbSession:  # Should not happen (except if session.reset has been called in the same request)
                    return False
                if dbSession["securityKey"] != key:  # Race-Condidtion: That skey has been used in another instance
                    return False
                dbSession["securityKey"] = utils.generateRandomString(13)
                db.Put(dbSession)
                return dbSession["securityKey"]

            try:
                newSkey = db.RunInTransaction(exchangeSecurityKey)
            except:  # This should be transaction collision
                return False
            if not newSkey:
                return False
            self.securityKey = newSkey
            self.changed = True
            return True
        return False

    def validateStaticSecurityKey(self, key: str) -> bool:
        """
        Checks if key matches the current *static* CSRF-Token of our session.
        """
        return hmac.compare_digest(self.staticSecurityKey, key)


@tasks.CallDeferred
def killSessionByUser(user: Optional[str] = None):
    """
        Invalidates all active sessions for the given *user*.

        This means that this user is instantly logged out.
        If no user is given, it tries to invalidate **all** active sessions.

        Use "guest" as to kill all sessions not associated with an user.

        :param user: UserID, "guest" or None.
    """
    logging.info(f"Invalidating all sessions for {user}")
    query = db.Query(Session.kindName)
    if user is not None:
        query.filter("user =", str(user))
    for obj in query.iter():
        db.Delete(obj.key)


@tasks.PeriodicTask(60 * 4)
def startClearSessions():
    """
        Removes old (expired) Sessions
    """
    doClearSessions(time.time() - (conf["viur.session.lifeTime"] + 300))


@tasks.CallDeferred
def doClearSessions(timeStamp: str) -> None:
    query = db.Query(Session.kindName).filter("lastseen <", timeStamp)
    for oldKey in query.run(100):
        db.Delete(oldKey)
    if query.getCursor():
        doClearSessions(timeStamp)
