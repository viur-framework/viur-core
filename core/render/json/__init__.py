from .default import DefaultRender as default
from .user import UserRender as user
from viur.core import securitykey, exposed
import json

__all__ = [default]


@exposed
def genSkey(*args, **kwargs) -> str:
    return json.dumps(securitykey.create())


def _postProcessAppObj(obj):  # Register our SKey function
    obj["skey"] = genSkey
    return obj
