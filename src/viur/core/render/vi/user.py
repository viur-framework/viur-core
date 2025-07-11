from viur.core import current
from viur.core.render.json.user import UserRender as user
import string, json


class UserRender(user):
    kind = "json.vi"

    def loginSucceeded(self, **kwargs):
        return json.dumps(kwargs.get("msg", "OKAY"))
