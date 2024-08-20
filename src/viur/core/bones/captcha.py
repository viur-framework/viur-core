import logging
import typing as t

import requests

from viur.core import conf, current
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity

if t.TYPE_CHECKING:
    from viur.core.skeleton import SkeletonInstance


class CaptchaBone(BaseBone):
    r"""
    The CaptchaBone is used to ensure that a user is not a bot.

    The Captcha bone uses the Google reCAPTCHA API to perform the Captcha
    validation and supports v2 and v3.

    .. seealso::

        Option :attr:`core.config.Security.captcha_default_credentials`
        for global security settings.

        Option :attr:`core.config.Security.captcha_enforce_always`
        for developing.
    """

    type = "captcha"

    def __init__(
        self,
        *,
        publicKey: str = None,
        privateKey: str = None,
        score_threshold: float = 0.5,
        **kwargs: t.Any
    ):
        """
        Initializes a new CaptchaBone.

        `publicKey` and `privateKey` can be omitted, if they are set globally
        in :attr:`core.config.Security.captcha_default_credentials`.

        :param publicKey: The public key for the Captcha validation.
        :param privateKey: The private key for the Captcha validation.
        :score_threshold: If reCAPTCHA v3 is used, the score must be at least this threshold.
            For reCAPTCHA v2 this property will be ignored.
        """
        super().__init__(**kwargs)
        self.defaultValue = self.publicKey = publicKey
        self.privateKey = privateKey
        if not (0 < score_threshold <= 1):
            raise ValueError("score_threshold must be between 0 and 1.")
        self.score_threshold = score_threshold
        if not self.defaultValue and not self.privateKey:
            # Merge these values from the side-wide configuration if set
            if conf.security.captcha_default_credentials:
                self.defaultValue = self.publicKey = conf.security.captcha_default_credentials["sitekey"]
                self.privateKey = conf.security.captcha_default_credentials["secret"]
        self.required = True
        if not self.privateKey:
            raise ValueError("privateKey must be set.")

    def serialize(self, skel: "SkeletonInstance", name: str, parentIndexed: bool) -> bool:
        """
        Serializing the Captcha bone is not possible so it return False
        """
        return False

    def unserialize(self, skel: "SkeletonInstance", name) -> t.Literal[True]:
        """
        Stores the publicKey in the SkeletonInstance

        :param skel: The target :class:`SkeletonInstance`.
        :param name: The name of the CaptchaBone in the :class:`SkeletonInstance`.

        :returns: boolean, that is true, as the Captcha bone is always unserialized successfully.
        """
        skel.accessedValues[name] = self.publicKey
        return True

    def fromClient(self, skel: "SkeletonInstance", name: str, data: dict) -> None | list[ReadFromClientError]:
        """
        Load the reCAPTCHA token from the provided data and validate it with the help of the API.

        reCAPTCHA provides the token via callback usually as "g-recaptcha-response",
        but to fit into the skeleton logic, we support both names.
        So the token can be provided as "g-recaptcha-response" or the name of the CaptchaBone in the Skeleton.
        While the latter one is the preferred name.
        """
        if not conf.security.captcha_enforce_always and conf.instance.is_dev_server:
            logging.info("Skipping captcha validation on development server")
            return None
        if not conf.security.captcha_enforce_always and (user := current.user.get()) and "root" in user["access"]:
            logging.info("Skipping captcha validation for root user")
            return None  # Don't bother trusted users with this (not supported by admin/vi anyway)
        if name not in data and "g-recaptcha-response" not in data:
            return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, "No Captcha given!")]

        result = requests.post(
            url="https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": self.privateKey,
                "remoteip": current.request.get().request.remote_addr,
                "response": data.get(name, data.get("g-recaptcha-response")),
            },
            timeout=10,
        )
        if not result.ok:
            logging.error(f"{result.status_code} {result.reason}: {result.text}")
            raise ValueError(f"Request to reCAPTCHA failed: {result.status_code} {result.reason}")
        data = result.json()
        logging.debug(f"Captcha verification {data=}")

        if not data.get("success"):
            logging.error(data.get("error-codes"))
            return [ReadFromClientError(
                ReadFromClientErrorSeverity.Invalid,
                f'Invalid Captcha: {", ".join(data.get("error-codes", []))}'
            )]

        if "score" in data and data["score"] < self.score_threshold:
            # it's reCAPTCHA v3; check the score
            return [ReadFromClientError(
                ReadFromClientErrorSeverity.Invalid,
                f'Invalid Captcha: {data["score"]} is lower than threshold {self.score_threshold}'
            )]

        return None  # okay
