import json
from viur.core.modules.user import UserSecondFactorAuthentication
from . import default as DefaultRender
from .default import CustomJsonEncoder


class UserRender(DefaultRender):  # Render user-data to json

    def login(self, skel, **kwargs):
        if kwargs.get("loginFailed", False):
            return json.dumps("FAILURE")
        return self.edit(skel, **kwargs)

    def loginSucceeded(self, msg="OKAY", **kwargs):
        return json.dumps(msg)

    def logoutSuccess(self, **kwargs):
        return json.dumps("OKAY")

    def verifySuccess(self, skel, **kwargs):
        return json.dumps("OKAY")

    def verifyFailed(self, **kwargs):
        return json.dumps("FAILED")

    def passwdRecoverInfo(self, msg, skel=None, tpl=None, **kwargs):
        if skel:
            return self.edit(skel, **kwargs)

        return json.dumps(msg)

    def passwdRecover(self, *args, **kwargs):
        return self.edit(*args, **kwargs)

    def second_factor_add(self, otp_uri=None, *args, **kwargs):
        return json.dumps({"otp_uri": otp_uri})

    def second_factor_add_success(self, *args, **kwargs):
        return json.dumps("OKAY")
