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
"""
