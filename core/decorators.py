from viur.core import errors, current
from typing import Callable, Dict, Union, List

import functools
import logging
import types
import warnings


def ensure_viur_flags(func: Callable) -> None:
    try:
        func.viur_flags
    except AttributeError:
        func.viur_flags = {}


def access(*access: str | list[str]) -> Callable:
    """Decorator, which performs the authentication and authorization check.

    To expose a method only to logged in users with the access
    "root" or ("admin" and "file-edit") or "maintainer"
    use this decorator like this:

    .. code-block:: python
        from viur.core.decorators import access
        @access("root", ["admin", "file-edit"], ["maintainer"])
        def yourMethod(self):
            return "You're allowed!"
    """

    def outer_wrapper(func: Callable):
        ensure_viur_flags(func)

        func.viur_flags["access"] = access

        @functools.wraps(func)
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
                    return func(*args, **kwargs)

            logging.error("%s requires access %s", func.__name__, " OR ".join(map(repr, access)))
            raise errors.Forbidden()

        return wrapper

    assert access, "No rules set"
    return outer_wrapper


def force_ssl(func: Callable) -> Callable:
    """
        Decorator, which forces usage of an encrypted Channel for a given resource.
        Has no effect on development-servers.
    """
    ensure_viur_flags(func)
    func.viur_flags["ssl"] = True
    return func


def require_skey(func=None, *, allow_empty: bool = False, forward_argument: str = "", **extra_kwargs: dict) -> Callable:
    """
    Decorator, which marks the function requires a skey.
    """

    def decorator(func: Callable) -> Callable:
        ensure_viur_flags(func)

        func.viur_flags["skey"] = {
            "allow_empty": allow_empty,
            "forward_argument": forward_argument,
            "kwargs": extra_kwargs,
        }

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not allow_empty and 'skey' not in kwargs:
                raise errors.PreconditionFailed()
            return func(*args, **kwargs)

        return wrapper

    if func is None:
        return decorator

    return decorator(func)


def force_post(func: Callable) -> Callable:
    """
        Decorator, which forces usage of an http post request.
    """

    ensure_viur_flags(func)
    func.viur_flags["method"] = ["POST"]
    return func


def exposed(func: Union[Callable, dict]) -> Callable:
    """
        Decorator, which marks an function as exposed.

        Only exposed functions are callable by http-requests.
        Can optionally receive a dict of language->translated name to make that function
        available under different names
    """

    if isinstance(func, dict):
        translation_map = func
        
        # We received said dictionary:
        def expose_with_translations(func: Callable) -> Callable:
            ensure_viur_flags(func)

            func.viur_flags["exposed"] = True
            if not ("method" in func.viur_flags):
                func.viur_flags["method"] = ["GET", "POST", "HEAD"]
            func.viur_flags["seoLanguageMap"] = translation_map
            return func

        return expose_with_translations

    ensure_viur_flags(func)

    func.viur_flags["exposed"] = True
    if not ("method" in func.viur_flags):
        func.viur_flags["method"] = ["GET", "POST", "HEAD"]

    func.viur_flags["seoLanguageMap"] = None

    return func


def internal_exposed(func: Callable) -> Callable:
    """
        Decorator, marks an function as internal exposed.

        Internal exposed functions are not callable by external http-requests,
        but can be called by templates using ``execRequest()``.
    """
    ensure_viur_flags(func)

    func.viur_flags["internal_exposed"] = True
    return func


def get_attr(attr: str) -> object:
    mapping = {
        "forcePost": ("force_post", force_post),
        "forceSSL": ("force_ssl", force_ssl),
        "internalExposed": ("internal_exposed", internal_exposed)
    }

    if entry := mapping.get(attr, None):
        func = entry[1]
        msg = f"{attr} was replaced by {entry[0]}"
        warnings.warn(msg, DeprecationWarning, stacklevel=3)
        logging.warning(msg, stacklevel=3)
        return func

    return None


def __getattr__(attr: str) -> object:
    if attribute := get_attr(attr):
        return attribute

    return super(__import__(__name__).__class__).__getattr__(attr)
