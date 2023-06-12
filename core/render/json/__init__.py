from .default import DefaultRender as default
from .user import UserRender as user
from viur.core import securitykey, current, errors, exposed
import json

__all__ = [default]


@exposed
def skey(duration: int = 60, *args, **kwargs) -> str:
    """
    Creates or returns a valid skey.

    When a user is authenticated, a duration can be provided,
    which returns a fresh, session-agnostic skey.
    Otherwise, a session-based skey is returned.

    See module securitykey for details.
    """
    current.request.get().response.headers["Content-Type"] = "application/json"

    if not 0 < duration <= 60:
        raise errors.Forbidden("Invalid duration provided")

    return json.dumps(securitykey.create(duration=duration))


def _postProcessAppObj(obj):  # Register our SKey function
    obj["skey"] = skey
    return obj
