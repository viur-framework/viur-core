import functools
import logging
from typing import Callable
from viur.core import errors, current


def __ensure_viur_flags(func: Callable) -> dict:
    try:
        return func.viur_flags
    except AttributeError:
        func.viur_flags = {}
        return func.viur_flags


def access(*access: str | list[str] | tuple[str] | set[str] | Callable, offer_login: bool | str = False) -> Callable:
    """Decorator, which performs an authentication and authorization check primarily based on the current user's access,
    which is defined via `UserSkel.access`.

    To check on authenticated users with the access "root" or ("admin" and "file-edit") or "maintainer" use the
    decorator like this:

    .. code-block:: python
        from viur.core.decorators import access
        @access("root", ["admin", "file-edit"], ["maintainer"])
        def your_method(self):
            return "You're allowed!"

    Furthermore, instead of a list/tuple/set/str, a callable can be provided which performs custom access checking,
    and directly is checked on True for access grant.
    """

    def outer_wrapper(func: Callable):
        __ensure_viur_flags(func)["access"] = access

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user = current.user.get()
            if not user:
                if offer_login:
                    raise errors.Redirect(offer_login if isinstance(offer_login, str) else "/user/login")

                raise errors.Unauthorized()

            for acc in access:
                # Callable directly tests access
                if callable(acc):
                    if acc():
                        return func(*args, **kwargs)

                    continue

                # Otherwise, check for access rights
                if isinstance(acc, str):
                    acc = (acc, )

                assert isinstance(acc, (tuple, list, set))

                if not set(acc).difference(user["access"]):
                    return func(*args, **kwargs)

            # logging.error("%s requires access %s", func.__name__, " OR ".join(map(repr, access)))
            raise errors.Forbidden()

        return wrapper

    assert access, "No rules set"
    return outer_wrapper


def force_ssl(func: Callable) -> Callable:
    """
    Decorator, which forces usage of an encrypted channel for a given resource.
    Has no effect on development-servers.
    """
    __ensure_viur_flags(func)["ssl"] = True
    return func


def require_skey(
    func: Callable = None,
    *,
    allow_empty: bool = False,
    forward_argument: str = "",
    **extra_kwargs: dict,
) -> Callable:
    """
    Decorator, which marks the function requires a skey.
    """

    def decorator(func: Callable) -> Callable:
        __ensure_viur_flags(func)["skey"] = {
            "allow_empty": allow_empty,
            "forward_argument": forward_argument,
            "kwargs": extra_kwargs,
        }

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not allow_empty and 'skey' not in kwargs:
                raise errors.PreconditionFailed("skey is missing")
            return func(*args, **kwargs)

        return wrapper

    if func is None:
        return decorator

    return decorator(func)


def force_post(func: Callable) -> Callable:
    """
    Decorator, which enforces usage of a http post request.
    """

    __ensure_viur_flags(func)["method"] = ["POST"]
    return func


def exposed(func: Callable | dict) -> Callable:
    """
    Decorator, which marks a function as exposed.

    Only exposed functions are callable by http-requests.
    Can optionally receive a dict of language->translated name to make that function
    available under different names
    """

    if isinstance(func, dict):
        translation_map = func

        # We received said dictionary:
        def expose_with_translations(func: Callable) -> Callable:
            flags = __ensure_viur_flags(func)
            flags["exposed"] = True
            if "method" not in flags:
                flags["method"] = ["GET", "POST", "HEAD"]
            flags["seoLanguageMap"] = translation_map

            return func

        return expose_with_translations

    flags = __ensure_viur_flags(func)
    flags["exposed"] = True
    if "method" not in flags:
        flags["method"] = ["GET", "POST", "HEAD"]
    flags["seoLanguageMap"] = None

    return func


def internal_exposed(func: Callable) -> Callable:
    """
    Decorator, marks a function as internal exposed.

    Internal exposed functions are not callable by external http-requests,
    but can be called by templates using ``execRequest()``.
    """
    __ensure_viur_flags(func)["internal_exposed"] = True
    return func
