import json
from . import default as DefaultRender


class UserRender(DefaultRender):  # Render user-data to json

    def login(self, skel, **kwargs):
        if kwargs.get("loginFailed", False):
            return json.dumps("FAILURE")
        return self.edit(skel, **kwargs)

    def loginChoices(self, authMethods, **kwargs):
        return json.dumps(list(set([x[0] for x in authMethods])))

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
