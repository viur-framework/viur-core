from viur.core import errors, current
from typing import Callable, Dict, Union, List

import functools
import logging
import types
import warnings


def ensure_viur_flags(f: Callable) -> None:
    try:
        f.viur_flags
    except AttributeError:
        f.viur_flags = {}


def access(*access: str|list[str]):
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
        ensure_viur_flags(f)

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
    ensure_viur_flags(f)
    f.viur_flags["ssl"] = True
    return f


def require_skey(func=None, *, allow_empty: bool = False, forward_argument: str = "", **extra_kwargs: dict) -> Callable:
    """
    Decorator, which marks the function requires a skey.
    """
    if func is None:
        return lambda func: require_skey(func, allow_empty=allow_empty, forward_argument=forward_argument, **extra_kwargs)

    def decorator(func: Callable) -> Callable:
        ensure_viur_flags(func)

        flags = {
            "empty": allow_empty,
            "forward_argument": forward_argument,
            "kwargs": extra_kwargs
        }

        func.viur_flags["skey"] = {
            "status": True,
            "flags": flags,
        }

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not allow_empty and 'skey' not in kwargs:
                raise ValueError("skey is required")
            return func(*args, **kwargs)
        
        return wrapper

    return decorator(func)


def force_post(f: Callable) -> Callable:
    """
        Decorator, which forces usage of an http post request.
    """

    ensure_viur_flags(f)

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
    ensure_viur_flags(f)

    if isinstance(f, dict):
        # We received said dictionary:
        def expose_with_translations(func: Callable) -> Callable:
            ensure_viur_flags(func)

            func.viur_flags["exposed"] = True
            if not ("method" in func.viur_flags):
                func.viur_flags["method"] = ["GET", "POST"]
            func.viur_flags["seoLanguageMap"] = f
            return g

        return expose_with_translations

    ensure_viur_flags(f)

    f.viur_flags["exposed"] = True
    if not ("method" in f.viur_flags):
        f.viur_flags["method"] = ["GET", "POST"]

    f.viur_flags["seoLanguageMap"] = None

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

def get_attr(attr: str) -> object:
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

    return None

def __getattr__(attr: str) -> object:
    if attribute := get_attr(attr):
        return attribute
    
    return super(__import__(__name__).__class__).__getattr__(attr)


