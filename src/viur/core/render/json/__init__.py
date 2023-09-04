from .default import DefaultRender as default
from .user import UserRender as user
from viur.core import securitykey, current, errors
from viur.core.decorators import *
import json

__all__ = [default]


@exposed
def skey(amount: int = 1, *args, **kwargs) -> str:
    """
    Creates CSRF-security-keys for transactions.

    All returned keys are associated with the session, therefore they cannot be used across sessions.
    The keys get a maximum lifetime of the session lifetime, afterward they become invalid.

    :param amount: Optional amount of securitykeys to create in a batch.
        `amount > 1` can only be used by authenticated users, for a maximum of 100 keys.

    See module securitykey for details.
    """
    current.request.get().response.headers["Content-Type"] = "application/json"

    if amount == 1:
        return json.dumps(securitykey.create())

    if not 0 < amount <= 100:
        raise errors.Forbidden("Invalid amount provided")

    if not current.user.get():
        raise errors.Forbidden("Batch securitykey creation is only available to authenticated users")

    return json.dumps([securitykey.create() for _ in range(amount)])


def _postProcessAppObj(obj):  # Register our SKey function
    obj["skey"] = skey
    return obj
