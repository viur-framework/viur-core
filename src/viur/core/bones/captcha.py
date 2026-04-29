import logging
import typing as t

import requests

from viur.core import conf, current
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity

from google.cloud import recaptchaenterprise_v1
from google.cloud.recaptchaenterprise_v1 import Assessment

if t.TYPE_CHECKING:
    from viur.core.skeleton import SkeletonInstance


class CaptchaBone(BaseBone):
    r"""
    The CaptchaBone validates reCAPTCHA Enterprise tokens to protect forms from bots.

    It uses the Google reCAPTCHA Enterprise API and supports both invisible (v3-style score-based)
    and visible (checkbox widget) challenges via the ``render_challenge`` parameter.

    The token is submitted by the client as the bone's field value and verified server-side
    against the configured site key. A configurable score threshold determines whether
    invisible challenges pass.

    .. seealso::

        `Google reCAPTCHA Enterprise setup
        <https://cloud.google.com/recaptcha/docs/set-up-non-google-cloud-environments-api-keys>`
        for creating a site key and enabling the API.

        Option :attr:`core.config.Security.captcha_default_credentials`
        for global security settings.

        Option :attr:`core.config.Security.captcha_enforce_always`
        to enforce validation even on development servers.
    """

    type = "captcha"

    def __init__(
        self,
        *,
        public_key: str = None,
        score_threshold: float = 0.5,
        render_challenge: bool = False,
        recaptcha_action="",
        **kwargs: t.Any
    ):
        """
        Initializes a new CaptchaBone.

        :param public_key: The reCAPTCHA Enterprise site key shown to the client.
            Can be omitted if set globally via :attr:`core.config.Security.captcha_default_credentials`.
        :param score_threshold: Minimum score (0–1) required for invisible challenges to pass.
            Ignored when ``render_challenge`` is ``True``.
        :param render_challenge: If ``True``, renders a visible checkbox widget instead of
            running an invisible background check.
        :param recaptcha_action: The action name passed to reCAPTCHA for analytics and scoring.
            Should match the action used on the client side.
        """
        super().__init__(**kwargs)
        if "publicKey" in kwargs:
            public_key = kwargs.pop("publicKey")
        self.public_key = public_key

        if not (0 < score_threshold <= 1):
            raise ValueError("score_threshold must be between 0 and 1.")
        self.render_challenge = render_challenge
        self.recaptcha_action = recaptcha_action
        self.score_threshold = score_threshold
        self.required = True

    def serialize(self, skel: "SkeletonInstance", name: str, parentIndexed: bool) -> bool:
        """
        Serializing the Captcha bone is not possible so it return False
        """
        return False

    def unserialize(self, skel: "SkeletonInstance", name) -> t.Literal[True]:
        """
        Stores the public_key in the SkeletonInstance

        :param skel: The target :class:`SkeletonInstance`.
        :param name: The name of the CaptchaBone in the :class:`SkeletonInstance`.

        :returns: boolean, that is true, as the Captcha bone is always unserialized successfully.
        """
        skel.accessedValues[name] = self.public_key
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

        client = recaptchaenterprise_v1.RecaptchaEnterpriseServiceClient()

        # Set the attributes of the event to be tracked.
        event = recaptchaenterprise_v1.Event()
        event.site_key = self.public_key
        if name in data:
            event.token = data[name]
        else:
            return [ReadFromClientError(
                ReadFromClientErrorSeverity.NotSet,
                "Token not set"
            )]
        assessment = recaptchaenterprise_v1.Assessment()
        assessment.event = event

        project_name = f"projects/{conf.instance.project_id}"

        # Create the assessment request.
        request = recaptchaenterprise_v1.CreateAssessmentRequest()
        request.assessment = assessment
        request.parent = project_name

        response = client.create_assessment(request)

        if not response.token_properties.valid:
            logging.info(
                "The CreateAssessment call failed because the token was "
                + "invalid for the following reasons: "
                + str(response.token_properties.invalid_reason)
            )
            return [ReadFromClientError(
                ReadFromClientErrorSeverity.Invalid,
                "Invalid Token"
            )]

        # Check if the expected action was executed.
        if response.token_properties.action != self.recaptcha_action:
            logging.info(
                "The action attribute in your reCAPTCHA tag does not match the action you are expecting to score"
            )
            return [ReadFromClientError(
                ReadFromClientErrorSeverity.Invalid,
                f"Invalid Action: {self.recaptcha_action}"
            )]
        else:
            # Retrieve the risk score and reasons.
            # For more information on interpreting the assessment, see:
            # https://cloud.google.com/recaptcha/docs/interpret-assessment
            if response.risk_analysis.score < self.score_threshold:
                return [ReadFromClientError(
                    ReadFromClientErrorSeverity.Invalid,
                    f"Invalid Captcha: {response.risk_analysis.score}"
                )]

        return None

    def structure(self) -> dict:
        return super().structure() | {
            "public_key": self.public_key,
            "render_challenge": self.render_challenge,
            "action": self.recaptcha_action
        }
