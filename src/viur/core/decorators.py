import functools
import logging
from typing import Callable
from viur.core import errors, current
from viur.core.module import Exposed


#def exposed(internal: bool = False) -> Callable:
def exposed(func: Callable) -> Callable:
    """
    Decorator, which marks a function as exposed.

    Only exposed functions are callable by http-requests.
    Can optionally receive a dict of language->translated name to make that function
    available under different names
    """
    '''
    if isinstance(param, dict):
        translation_map = param

        # We received said dictionary:
        def expose_with_translations(func: Callable) -> Callable:
            flags = __ensure_viur_flags(func)
            flags["exposed"] = True
            if "method" not in flags:
                flags["method"] = ["GET", "POST", "HEAD"]
            flags["seoLanguageMap"] = translation_map

            return func

        return expose_with_translations

    elif isinstance(param, bool):
        def exposed_wrapper(func):
    '''

    func = Exposed.ensure(func)
    return func


def internal_exposed(func: Callable) -> Callable:
    """
    Decorator, which marks a function as internal exposed.
    """
    func = Exposed.ensure(func)
    func.internal = True
    return func


def force_ssl(func: Callable) -> Callable:
    """
    Decorator, which enforces usage of an encrypted channel for a given resource.
    Has no effect on development-servers.
    """
    func = Exposed.ensure(func)
    func.ssl = True
    return func


def force_post(func: Callable) -> Callable:
    """
    Decorator, which enforces usage of a http post request.
    """
    exposed = Exposed.ensure(func)
    exposed.methods = ("POST", )
    return exposed


def access(
    *access: str | list[str] | tuple[str] | set[str] | Callable,
    offer_login: bool | str = False,
    message: str | None = None,
) -> Callable:
    """Decorator, which performs an authentication and authorization check primarily based on the current user's access,
    which is defined via `UserSkel.access`.

    :params access: Access configuration, either names of access rights or a callable for verification.
    :params offer_login: Offers a way to login; Either set it to True, to automatically redirect to /user/login,
        or set it to any other URL.
    :params message: A custom message to be printed when access is denied or unauthorized.

    To check on authenticated users with the access "root" or ("admin" and "file-edit") or "maintainer" use the
    decorator like this:

    .. code-block:: python
        from viur.core.decorators import access
        @access("root", ["admin", "file-edit"], ["maintainer"])
        def my_method(self):
            return "You're allowed!"

    Furthermore, instead of a list/tuple/set/str, a callable can be provided which performs custom access checking,
    and directly is checked on True for access grant.
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user = current.user.get()
            if not user:
                if offer_login:
                    raise errors.Redirect(offer_login if isinstance(offer_login, str) else "/user/login")

                raise errors.Unauthorized(message) if message else errors.Unauthorized()

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
            raise errors.Forbidden(message) if message else errors.Forbidden()

        return wrapper

    assert access, "No rules set"
    return decorator


def skey(
    func: Callable = None,
    *,
    allow_empty: bool = False,
    forward_payload: str | None = None,
    message: str = "Missing or invalid skey",
    **extra_kwargs: dict,
) -> Callable:
    """
    Decorator, which marks the function requires a skey.
    """

    def decorator(func: Callable) -> Callable:
        def check(*args, **kwargs):
            # Here we will check the skey always before processing the request, because it cannot be empty.
            check = True

            # If the skey data can allow empty kwargs
            if allow_empty:
                # Only check the skey, if the kwargs is not empty
                check = bool(kwargs)

            if check:
                from viur.core import securitykey
                payload = securitykey.validate(kwargs.get("skey", ""), **extra_kwargs)

                if not payload:
                    raise errors.PreconditionFailed(message) if message else errors.PreconditionFailed()

                if forward_payload:
                    kwargs |= {forward_payload: payload}

        func = Exposed.ensure(func)
        func.skey = check
        return func

    if func is None:
        return decorator

    return decorator(func)
