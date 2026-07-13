"""
Token-based ("magic link") primary authentication for ViUR user modules.

``LoginKey`` authenticates a user by a secret token stored as an indexed
``CredentialBone`` on the user skeleton.  The caller submits the token as a
POST parameter; the handler looks up the matching user, validates the account
state, and completes the authentication flow.

Typical use cases include magic-link email logins, CLI tool authentication,
and service-to-service auth where a shared secret is acceptable.

Usage::

    from viur.core.modules.user import User
    from viur.core.contrib.loginkey import LoginKey

    class MyUser(User):
        authenticationProviders = [LoginKey, ...]

.. warning::
    An indexed :class:`~viur.core.bones.CredentialBone` allows any caller
    with Datastore read access to enumerate users by key.  Only deploy this
    in environments where that access is appropriately restricted, and always
    use long (≥ 32 char), randomly generated tokens.
"""
import logging

from viur.core import current, errors
from viur.core.bones import CredentialBone
from viur.core.decorators import exposed, force_post, force_ssl, skey
from viur.core.modules.user import Status, UserPrimaryAuthentication
from viur.core.ratelimit import RateLimit
from viur.core.skeleton import SkeletonInstance

logger = logging.getLogger(__name__)


class IndexedCredentialBone(CredentialBone):
    """A :class:`~viur.core.bones.CredentialBone` that is always Datastore-indexed.

    Regular ``CredentialBone`` values are excluded from indexes for security.
    This subclass forces indexing so that the value can be used as a filter
    criterion (e.g. ``filter("login_key =", token)``).

    .. note::
        Accepting an indexed credential is a deliberate trade-off: it enables
        server-side token lookup at the cost of exposing the value to anyone
        with Datastore read access.  Only use this when that trade-off is
        explicitly acceptable.
    """

    def serialize(self, skel: "SkeletonInstance", name: str, parentIndexed: bool) -> bool:
        skel.dbEntity.exclude_from_indexes.discard(name)  # force index even though it's a credential
        if name in skel.accessedValues and skel.accessedValues[name]:
            skel.dbEntity[name] = skel.accessedValues[name]
            return True
        return False


class LoginKey(UserPrimaryAuthentication):
    """Primary authentication via a secret login token.

    The token is stored in a ``login_key`` bone on the user skeleton
    (added automatically by :meth:`patch_user_skel`).  Failed attempts are
    rate-limited per IP address; successful logins are *not* counted against
    the quota.

    :cvar METHOD_NAME: HTTP header name used to identify this auth method.
    :cvar loginRateLimit: Allows 12 failed attempts per minute per IP.
    """

    METHOD_NAME = "X-AUTH-LOGINKEY"
    NAME = "LoginKey"

    # 12 failed attempts per minute, IP-based
    loginRateLimit = RateLimit("user.loginkey", 12, 1, "ip")

    @classmethod
    def patch_user_skel(cls, skel_cls):
        skel_cls.login_key = IndexedCredentialBone(
            descr="LoginKey",
            params={"category": "Authentication"},
            min_length=32,
        )

    @exposed
    @force_ssl
    @force_post
    @skey()
    def login(self, *, key: str, **kwargs):
        if current.user.get():
            return self._user_module.render.loginSucceeded()

        self.loginRateLimit.assertQuotaIsAvailable()

        user_skel = self._user_module.baseSkel()
        user_skel = user_skel.all().filter("login_key =", key).getSkel()

        is_okay = user_skel is not None
        logger.debug(f"user found: {is_okay=}")

        is_okay = is_okay and (user_skel["status"] or 0) >= Status.ACTIVE.value
        logger.debug(f"account active: {is_okay=}")

        is_okay = is_okay and len(str(user_skel.dbEntity["login_key"])) >= 32
        logger.debug(f"key length ok: {is_okay=}")

        is_okay = is_okay and ("root" not in user_skel["access"])
        logger.debug(f"not root: {is_okay=}")

        if not is_okay:
            self.loginRateLimit.decrementQuota()  # only failed attempts count
            raise errors.Unauthorized()

        return self.next_or_finish(user_skel)
