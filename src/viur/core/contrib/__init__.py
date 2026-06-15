"""
viur.core.contrib — optional, reusable application-level components.

This package contains self-contained components that are commonly needed
but *not* required to run a ViUR application.  Components are opt-in;
import only what you use.

Available modules
-----------------
loginkey
    :class:`~viur.core.contrib.loginkey.IndexedCredentialBone` and
    :class:`~viur.core.contrib.loginkey.LoginKey` — a
    :class:`~viur.core.modules.user.UserPrimaryAuthentication` that
    authenticates users via a secret token stored in a Datastore-indexed
    :class:`~viur.core.bones.CredentialBone`.  Suitable for "magic link"
    style logins or machine-to-machine auth.

Usage example::

    from viur.core.modules.user import User
    from viur.core.contrib.loginkey import LoginKey

    class MyUser(User):
        authenticationProviders = [LoginKey, ...]

ratelimit
    :class:`~viur.core.contrib.ratelimit.RequestRateLimit` — a
    :class:`~viur.core.request.RequestValidator` that enforces per-IP /
    per-user request-rate limits using App Engine Memcache.  Suitable for
    global rate-limiting and basic DDoS mitigation at the WSGI boundary.

Usage example::

    from viur.core.request import Router
    from viur.core.contrib.ratelimit import RequestRateLimit, TimeWindow

    Router.requestValidators.append(
        RequestRateLimit(
            rate_for_guests=TimeWindow(limit=200, time_window=60),
            rate_for_users=TimeWindow(limit=500, time_window=60),
        )
    )
"""
