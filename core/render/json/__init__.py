from .default import DefaultRender as default
from .user import UserRender as user
from viur.core import securitykey, current, errors, exposed
import json
import typing

__all__ = [default]


@exposed
def skey(duration: typing.Optional[int] = None, *args, **kwargs) -> str:
    """
    Creates or returns a valid skey.

    When a user is authenticated, a duration can be provided,
    which returns a fresh, session-agnostic skey.
    Otherwise, a session-based skey is returned.

    See module securitykey for details.
    """
    current.request.get().response.headers["Content-Type"] = "application/json"

    if duration is not None:
        if not current.user.get():
            raise errors.Unauthorized("Durations can only be used by authenticated users")

        if not 0 < duration <= 60:
            raise errors.Forbidden("Invalid duration provided")

    return json.dumps(securitykey.create(duration=duration))


def _postProcessAppObj(obj):  # Register our SKey function
    obj["skey"] = skey
    return obj
