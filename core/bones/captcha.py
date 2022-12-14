import json
import urllib.parse
import urllib.request
from typing import List, Union
from viur.core import utils, conf
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.utils import currentRequest


class CaptchaBone(BaseBone):
    type = "captcha"

    def __init__(self, *, publicKey=None, privateKey=None, **kwargs):
        super().__init__(**kwargs)
        self.defaultValue = self.publicKey = publicKey
        self.privateKey = privateKey
        if not self.defaultValue and not self.privateKey:
            # Merge these values from the side-wide configuration if set
            if conf["viur.security.captcha.defaultCredentials"]:
                self.defaultValue = self.publicKey = conf["viur.security.captcha.defaultCredentials"]["sitekey"]
                self.privateKey = conf["viur.security.captcha.defaultCredentials"]["secret"]
        self.required = True

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        return False

    def unserialize(self, skel, name) -> bool:
        skel.accessedValues[name] = self.publicKey
        return True

    def fromClient(self, skel: 'SkeletonInstance', name: str, data: dict) -> Union[None, List[ReadFromClientError]]:
        """
            Reads a value from the client.
            If this value is valid for this bone,
            store this value and return None.
            Otherwise our previous value is
            left unchanged and an error-message
            is returned.

            :param name: Our name in the skeleton
            :param data: *User-supplied* request-data
            :returns: None or a list of errors
        """
        if conf["viur.instance.is_dev_server"]:  # We dont enforce captchas on dev server
            return None
        user = utils.getCurrentUser()
        if user and "root" in user["access"]:
            return None  # Don't bother trusted users with this (not supported by admin/vi anyways)
        if not "g-recaptcha-response" in data:
            return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, "No Captcha given!")]
        data = {
            "secret": self.privateKey,
            "remoteip": currentRequest.get().request.remote_addr,
            "response": data["g-recaptcha-response"]
        }
        req = urllib.request.Request(url="https://www.google.com/recaptcha/api/siteverify",
                                     data=urllib.parse.urlencode(data).encode(),
                                     method="POST")
        response = urllib.request.urlopen(req)
        if json.loads(response.read()).get("success"):
            return None
        return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid Captcha")]
