import functools
import logging
from typing import Callable
from viur.core import errors, current
from viur.core.module import Method


# def exposed(internal: bool = False) -> Callable:
def exposed(func: Callable) -> Method:
    """
    Decorator, which marks a function as exposed.

    Only exposed functions are callable by http-requests.
    Can optionally receive a dict of language->translated name to make that function
    available under different names
    """
    if isinstance(func, dict):
        seo_language_map = func

        # We received said dictionary:
        def expose_with_translations(func: Callable) -> Method:
            func = Method.ensure(func)
            func.seo_language_map = seo_language_map
            return func

        return expose_with_translations

    func = Method.ensure(func)
    return func


def internal_exposed(func: Callable) -> Method:
    """
    Decorator, which marks a function as internal exposed.
    """
    func = Method.ensure(func)
    func.internal = True
    return func


def force_ssl(func: Callable) -> Method:
    """
    Decorator, which enforces usage of an encrypted channel for a given resource.
    Has no effect on development-servers.
    """
    func = Method.ensure(func)
    func.ssl = True
    return func


def force_post(func: Callable) -> Method:
    """
    Decorator, which enforces usage of a http post request.
    """
    exposed = Method.ensure(func)
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
    message: str = None,
    name: str = "skey",
    validate: Callable | None = None,
    **extra_kwargs: dict,
) -> Method:
    """
    Decorator, which configures a method for requiring a CSRF-security-key.
    """

    def decorator(func: Callable) -> Callable:
        def check(args, kwargs):
            # validation is necessary?
            if not allow_empty or args or kwargs:
                from viur.core import securitykey
                payload = securitykey.validate(kwargs.pop(name, ""), **extra_kwargs)

                if not payload or (validate and not validate(payload)):
                    raise errors.PreconditionFailed(message or f"Missing or invalid parameter {name!r}")

                if forward_payload:
                    kwargs |= {forward_payload: payload}

        func = Method.ensure(func)
        func.skey = check
        return func

    if func is None:
        return decorator

    return decorator(func)
