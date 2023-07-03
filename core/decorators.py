from viur.core import errors, current
from typing import Callable, Dict, Union, List

import functools
import logging
import types
import warnings


def access(*access):
    """Decorator, which performs the authentication and authorization check.

    To expose a method only to logged in users with the access
    "root" or ("admin" and "file-edit") or "maintainer"
    use this decorator like this:

    >>> from viur.core.decorators import access
    >>> @access("root", ["admin", "file-edit"], ["maintainer"])
    >>> def yourMethod(self):
    >>>		return "You're allowed!"
    """

    def outer_wrapper(f):
        try:
            f.viur_flags
        except AttributeError:
            f.viur_flags = {}

        f.viur_flags["access"] = access
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            user = current.user.get()
            if not user:
                raise errors.Unauthorized()

            for acc in access:
                if isinstance(acc, str):
                    acc = [acc]
                assert isinstance(acc, (tuple, list, set))

                missing_access = set(acc).difference(user["access"])
                if not missing_access:
                    return f(*args, **kwargs)

            logging.error("%s requires access %s", f.__name__, " OR ".join(map(repr, access)))
            raise errors.Forbidden()

        return wrapper

    assert access, "No rules set"
    return outer_wrapper

def force_ssl(f: Callable) -> Callable:
    """
        Decorator, which forces usage of an encrypted Channel for a given resource.
        Has no effect on development-servers.
    """
    try:
        f.viur_flags
    except AttributeError:
        f.viur_flags = {}

    f.viur_flags["ssl"] = True
    return f


def require_skey(allow_empty=False):
    """
        Decorator, which marks the function requires a skey.
        Important: this decorator dont check the skey in the params, it only marks it.  
    """
    def decorator(func: Callable) -> Callable:
        try:
            func.viur_flags
        except AttributeError:
            func.viur_flags = {}

        flags = {
            "empty": allow_empty
        }

        func.viur_flags["skey"] = {
            "status": True,
            "flags": flags,
        }

        def wrapper(*args, **kwargs):
            if not allow_empty and 'skey' not in kwargs:
                raise ValueError("skey is required")
            return func(*args, **kwargs)
        return wrapper

    return decorator


def force_post(f: Callable) -> Callable:
    """
        Decorator, which forces usage of an http post request.
    """

    try:
        f.viur_flags
    except AttributeError:
        f.viur_flags = {}

    if "method" in f.viur_flags:
        if "GET" in f.viur_flags["method"]:
            f.viur_flags["method"].remove("GET")
    else:
        f.viur_flags["method"] = ["POST"]

    return f


def exposed(f: Union[Callable, dict]) -> Callable:
    """
        Decorator, which marks an function as exposed.

        Only exposed functions are callable by http-requests.
        Can optionally receive a dict of language->translated name to make that function
        available under different names
    """
    if isinstance(f, dict):
        # We received said dictionary:
        def exposeWithTranslations(g):
            g.exposed = True
            try:
                g.viur_flags
            except AttributeError:
                g.viur_flags = {}

            g.viur_flags["exposed"] = True
            if not ("method" in f.viur_flags):
                g.viur_flags["method"] = ["GET", "POST"]
            g.seoLanguageMap = f
            return g

        return exposeWithTranslations

    try:
        f.viur_flags
    except AttributeError:
        f.viur_flags = {}

    f.viur_flags["exposed"] = True
    if not ("method" in f.viur_flags):
        f.viur_flags["method"] = ["GET", "POST"]

    #f.exposed = True
    #f.seoLanguageMap = None
    return f


def internal_exposed(f: Callable) -> Callable:
    """
        Decorator, marks an function as internal exposed.

        Internal exposed functions are not callable by external http-requests,
        but can be called by templates using ``execRequest()``.
    """
    try:
        f.viur_flags
    except AttributeError:
        f.viur_flags = {}

    f.viur_flags["internal_exposed"] = True
    return f

def get_attr(attr):
    if attr in ("forcePost", "forceSSL", "internalExposed"):
        ret = None
        msg = ""
        match attr:
            case "forcePost":
                msg = "forcePost was replaced by force_post"
                ret = force_post
            case "forceSSL":
                msg = "forceSSL was replaced by force_ssl"
                ret = force_ssl
            case "internalExposed":
                msg = "internalExposed was replaced by internal_exposed"
                ret = internal_exposed

        if ret:
            warnings.warn(msg, DeprecationWarning, stacklevel=3)
            logging.warning(msg, stacklevel=3)
            return ret

    return super(__import__(__name__).__class__).__getattr__(attr)

__getattr__ = get_attr

