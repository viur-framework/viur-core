import json
import urllib.parse
import urllib.request
import typing as t

from viur.core import conf, current
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity


class CaptchaBone(BaseBone):
    r"""
    The CaptchaBone is used to ensure that a user is not a bot.

    The Captcha bone uses the Google reCAPTCHA API to perform the Captcha
    validation and is derived from the BaseBone.

    :param publicKey: The public key for the Captcha validation.
    :param privateKey: The private key for the Captcha validation.
    :param \**kwargs: Additional arguments to pass to the base class constructor.
    """
    type = "captcha"

    def __init__(self, *, publicKey=None, privateKey=None, **kwargs):
        super().__init__(**kwargs)
        self.defaultValue = self.publicKey = publicKey
        self.privateKey = privateKey
        if not self.defaultValue and not self.privateKey:
            # Merge these values from the side-wide configuration if set
            if conf.security.captcha_default_credentials:
                self.defaultValue = self.publicKey = conf.security.captcha_default_credentials["sitekey"]
                self.privateKey = conf.security.captcha_default_credentials["secret"]
        self.required = True

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        """
        Serializing the Captcha bone is not possible so it return False
        """
        return False

    def unserialize(self, skel, name) -> bool:
        """
        Unserialize the Captcha bone.

        :param skel: The SkeletonInstance containing the Captcha bone.
        :param name: The name of the Captcha bone.

        :returns: boolean, that is true, as the Captcha bone is always unserialized successfully.
        """
        skel.accessedValues[name] = self.publicKey
        return True

    def fromClient(self, skel: 'SkeletonInstance', name: str, data: dict) -> None | list[ReadFromClientError]:
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
        if conf.instance.is_dev_server:  # We dont enforce captchas on dev server
            return None
        if (user := current.user.get()) and "root" in user["access"]:
            return None  # Don't bother trusted users with this (not supported by admin/vi anyways)
        if not "g-recaptcha-response" in data:
            return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, "No Captcha given!")]
        data = {
            "secret": self.privateKey,
            "remoteip": current.request.get().request.remote_addr,
            "response": data["g-recaptcha-response"]
        }
        req = urllib.request.Request(url="https://www.google.com/recaptcha/api/siteverify",
                                     data=urllib.parse.urlencode(data).encode(),
                                     method="POST")
        response = urllib.request.urlopen(req)
        if json.loads(response.read()).get("success"):
            return None
        return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid Captcha")]
