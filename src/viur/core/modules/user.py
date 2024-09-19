import abc
import datetime
import enum
import functools
import hashlib
import hmac
import json
import logging
import secrets
import warnings
import user_agents

import pyotp
import base64
import dataclasses
import typing as t
from google.auth.transport import requests
from google.oauth2 import id_token

from viur.core import (
    conf, current, db, email, errors, i18n,
    securitykey, session, skeleton, tasks, utils, Module
)
from viur.core.decorators import *
from viur.core.bones import *
from viur.core.bones.password import PBKDF2_DEFAULT_ITERATIONS, encode_password
from viur.core.prototypes.list import List
from viur.core.ratelimit import RateLimit
from viur.core.securityheaders import extendCsp


@functools.total_ordering
class Status(enum.Enum):
    """Status enum for a user

    Has backwards compatibility to be comparable with non-enum values.
    Will be removed with viur-core 4.0.0
    """

    UNSET = 0  # Status is unset
    WAITING_FOR_EMAIL_VERIFICATION = 1  # Waiting for email verification
    WAITING_FOR_ADMIN_VERIFICATION = 2  # Waiting for verification through admin
    DISABLED = 5  # Account disabled
    ACTIVE = 10  # Active

    def __eq__(self, other):
        if isinstance(other, Status):
            return super().__eq__(other)
        return self.value == other

    def __lt__(self, other):
        if isinstance(other, Status):
            return super().__lt__(other)
        return self.value < other


class UserSkel(skeleton.Skeleton):
    kindName = "user"  # this assignment is required, as this Skeleton is defined in viur-core (see #604)

    name = EmailBone(
        descr="E-Mail",
        required=True,
        readOnly=True,
        caseSensitive=False,
        searchable=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, True, "Username already taken"),
    )

    firstname = StringBone(
        descr="Firstname",
        searchable=True,
    )

    lastname = StringBone(
        descr="Lastname",
        searchable=True,
    )

    roles = SelectBone(
        descr=i18n.translate("viur.user.bone.roles", defaultText="Roles"),
        values=conf.user.roles,
        required=True,
        multiple=True,
        # fixme: This is generally broken in VIUR! See #776 for details.
        # vfunc=lambda values:
        #     i18n.translate(
        #         "user.bone.roles.invalid",
        #         defaultText="Invalid role setting: 'custom' can only be set alone.")
        #     if "custom" in values and len(values) > 1 else None,
        defaultValue=list(conf.user.roles.keys())[:1],
    )

    access = SelectBone(
        descr=i18n.translate("viur.user.bone.access", defaultText="Access rights"),
        type_postfix="access",
        values=lambda: {
            right: i18n.translate(f"server.modules.user.accessright.{right}", defaultText=right)
            for right in sorted(conf.user.access_rights)
        },
        multiple=True,
        params={
            "readonlyIf": "'custom' not in roles"  # if "custom" is not in roles, "access" is managed by the role system
        }
    )

    status = SelectBone(
        descr="Account status",
        values=Status,
        defaultValue=Status.ACTIVE,
        required=True,
    )

    lastlogin = DateBone(
        descr="Last Login",
        readOnly=True,
    )

    admin_config = JsonBone(  # This bone stores settings from the vi
        descr="Config for the User",
        visible=False
    )

    def __new__(cls):
        """
        Constructor for the UserSkel-class, with the capability
        to dynamically add bones required for the configured
        authentication methods.
        """
        for provider in conf.main_app.vi.user.authenticationProviders:
            assert issubclass(provider, UserPrimaryAuthentication)
            provider.patch_user_skel(cls)

        for provider in conf.main_app.vi.user.secondFactorProviders:
            assert issubclass(provider, UserSecondFactorAuthentication)
            provider.patch_user_skel(cls)

        cls.__boneMap__ = skeleton.MetaBaseSkel.generate_bonemap(cls)
        return super().__new__(cls)

    @classmethod
    def toDB(cls, skel, *args, **kwargs):
        # Roles
        if skel["roles"] and "custom" not in skel["roles"]:
            # Collect access rights through rules
            access = set()

            for role in skel["roles"]:
                # Get default access for this role
                access |= conf.main_app.vi.user.get_role_defaults(role)

                # Go through all modules and evaluate available role-settings
                for name in dir(conf.main_app.vi):
                    if name.startswith("_"):
                        continue

                    module = getattr(conf.main_app.vi, name)
                    if not isinstance(module, Module):
                        continue

                    roles = getattr(module, "roles", None) or {}
                    rights = roles.get(role, roles.get("*", ()))

                    # Convert role into tuple if it's not
                    if not isinstance(rights, (tuple, list)):
                        rights = (rights, )

                    if "*" in rights:
                        for right in module.accessRights:
                            access.add(f"{name}-{right}")
                    else:
                        for right in rights:
                            if right in module.accessRights:
                                access.add(f"{name}-{right}")

                                # special case: "edit" and "delete" actions require "view" as well!
                                if right in ("edit", "delete") and "view" in module.accessRights:
                                    access.add(f"{name}-view")

            skel["access"] = list(access)

        return super().toDB(skel, *args, **kwargs)


class UserAuthentication(Module, abc.ABC):
    @property
    @abc.abstractstaticmethod
    def METHOD_NAME() -> str:
        """
        Define a unique method name for this authentication.
        """
        ...

    def __init__(self, moduleName, modulePath, userModule):
        super().__init__(moduleName, modulePath)
        self._user_module = userModule

    def can_handle(self, skel: skeleton.SkeletonInstance) -> bool:
        return True

    @classmethod
    def patch_user_skel(cls, skel_cls: skeleton.Skeleton):
        """
        Allows for an UserAuthentication to patch the UserSkel
        class with additional bones which are required for
        the implemented authentication method.
        """
        ...


class UserPrimaryAuthentication(UserAuthentication, abc.ABC):
    """Abstract class for all primary authentication methods."""
    registrationEnabled = False

    @abc.abstractmethod
    def login(self, *args, **kwargs):
        ...

    def next_or_finish(self, skel: skeleton.SkeletonInstance):
        """
        Hook that is called whenever a part of the authentication was successful.
        It allows to perform further steps in custom authentications,
        e.g. change a password after first login.
        """
        return self._user_module.continueAuthenticationFlow(self, skel["key"])


class UserPassword(UserPrimaryAuthentication):
    METHOD_NAME = "X-VIUR-AUTH-User-Password"

    registrationEmailVerificationRequired = True
    registrationAdminVerificationRequired = True

    verifySuccessTemplate = "user_verify_success"
    verifyEmailAddressMail = "user_verify_address"
    verifyFailedTemplate = "user_verify_failed"
    passwordRecoveryTemplate = "user_passwordrecover"
    passwordRecoveryMail = "user_password_recovery"
    passwordRecoverySuccessTemplate = "user_passwordrecover_success"
    passwordRecoveryStep1Template = "user_passwordrecover_step1"
    passwordRecoveryStep2Template = "user_passwordrecover_step2"
    passwordRecoveryStep3Template = "user_passwordrecover_step3"

    # The default rate-limit for password recovery (10 tries each 15 minutes)
    passwordRecoveryRateLimit = RateLimit("user.passwordrecovery", 10, 15, "ip")

    # Limit (invalid) login-retries to once per 5 seconds
    loginRateLimit = RateLimit("user.login", 12, 1, "ip")

    @classmethod
    def patch_user_skel(cls, skel_cls):
        """
        Modifies the UserSkel to be equipped by a PasswordBone.
        """
        skel_cls.password = PasswordBone(
            readOnly=True,
            visible=False,
            params={
                "category": "Authentication",
            }
        )

    class LoginSkel(skeleton.RelSkel):
        name = EmailBone(
            descr="E-Mail",
            required=True,
            caseSensitive=False,
        )
        password = PasswordBone(
            required=True,
            test_threshold=0,
        )

    class LostPasswordStep1Skel(skeleton.RelSkel):
        name = EmailBone(
            descr="E-Mail",
            required=True,
        )

    class LostPasswordStep2Skel(skeleton.RelSkel):
        recovery_key = StringBone(
            descr="Recovery Key",
            required=True,
            params={
                "tooltip": i18n.translate(
                    key="viur.modules.user.userpassword.lostpasswordstep2.recoverykey",
                    defaultText="Please enter the validation key you've received via e-mail.",
                    hint="Shown when the user needs more than 15 minutes to paste the key",
                ),
            }
        )

    class LostPasswordStep3Skel(skeleton.RelSkel):
        # send the recovery key again, in case the password is rejected by some reason.
        recovery_key = StringBone(
            descr="Recovery Key",
            visible=False,
            readOnly=True,
        )

        password = PasswordBone(
            descr="New Password",
            required=True,
            params={
                "tooltip": i18n.translate(
                    key="viur.modules.user.userpassword.lostpasswordstep3.password",
                    defaultText="Please enter a new password for your account.",
                ),
            }
        )

    @exposed
    @force_ssl
    @skey(allow_empty=True)
    def login(self, *, name: str | None = None, password: str | None = None, **kwargs):
        if current.user.get():  # User is already logged in, nothing to do.
            return self._user_module.render.loginSucceeded()

        if not name or not password:
            return self._user_module.render.login(self.LoginSkel(), action="login")

        self.loginRateLimit.assertQuotaIsAvailable()

        # query for the username. The query might find another user, but the name is being checked for equality below
        name = name.lower().strip()
        user_skel = self._user_module.baseSkel()
        user_skel = user_skel.all().filter("name.idx >=", name).getSkel() or user_skel

        # extract password hash from raw database entity (skeleton access blocks it)
        password_data = (user_skel.dbEntity and user_skel.dbEntity.get("password")) or {}
        iterations = password_data.get("iterations", 1001)  # remember iterations; old password hashes used 1001
        password_hash = encode_password(password, password_data.get("salt", "-invalid-"), iterations)["pwhash"]

        # now check if the username matches
        is_okay = secrets.compare_digest((user_skel["name"] or "").lower().strip().encode(), name.encode())

        # next, check if the password hash matches
        is_okay &= secrets.compare_digest(password_data.get("pwhash", b"-invalid-"), password_hash)

        # next, check if the user account is active
        is_okay &= (user_skel["status"] or 0) >= Status.ACTIVE.value

        if not is_okay:
            self.loginRateLimit.decrementQuota()  # Only failed login attempts will count to the quota
            skel = self.LoginSkel()
            return self._user_module.render.login(
                skel,
                action="login",
                loginFailed=True,  # FIXME: Is this still being used?
                accountStatus=user_skel["status"]  # FIXME: Is this still being used?
            )

        # check if iterations are below current security standards, and update if necessary.
        if iterations < PBKDF2_DEFAULT_ITERATIONS:
            logging.info(f"Update password hash for user {name}.")
            # re-hash the password with more iterations
            # FIXME: This must be done within a transaction!
            user_skel["password"] = password  # will be hashed on serialize
            user_skel.toDB(update_relations=False)

        return self.next_or_finish(user_skel)

    @exposed
    def pwrecover(self, recovery_key: str | None = None, skey: str | None = None, *args, **kwargs):
        """
            This implements a password recovery process which lets users set a new password for their account,
            after validating a recovery key sent by email.

            The process is as following:

            - The user enters his email adress
            - We'll generate a random code and store it as a security-key and call sendUserPasswordRecoveryCode
            - sendUserPasswordRecoveryCode will run in the background, check if we have a user with that name
              and send a link with the code . It runs as a deferredTask so we don't leak the information if a user
              account exists.
            - If the user received his email, he can click on the link and set a new password for his account.

            To prevent automated attacks, the fist step is guarded by a captcha and we limited calls to this function
            to 10 actions per 15 minutes. (One complete recovery process consists of two calls).
        """
        self.passwordRecoveryRateLimit.assertQuotaIsAvailable()
        current_request = current.request.get()

        if recovery_key is None:
            # This is the first step, where we ask for the username of the account we'll going to reset the password on
            skel = self.LostPasswordStep1Skel()

            if not current_request.isPostRequest or not skel.fromClient(kwargs):
                return self._user_module.render.edit(skel, tpl=self.passwordRecoveryStep1Template)

            # validate security key
            if not securitykey.validate(skey):
                raise errors.PreconditionFailed()

            self.passwordRecoveryRateLimit.decrementQuota()

            recovery_key = securitykey.create(
                duration=datetime.timedelta(minutes=15),
                key_length=conf.security.password_recovery_key_length,
                user_name=skel["name"].lower(),
                session_bound=False,
            )

            # Send the code in background
            self.sendUserPasswordRecoveryCode(
                skel["name"], recovery_key, current_request.request.headers["User-Agent"]
            )

            # step 2 is only an action-skel, and can be ignored by a direct link in the
            # e-mail previously sent. It depends on the implementation of the specific project.
            return self._user_module.render.edit(
                self.LostPasswordStep2Skel(),
                tpl=self.passwordRecoveryStep2Template,
            )

        # in step 3
        skel = self.LostPasswordStep3Skel()
        skel["recovery_key"] = recovery_key  # resend the recovery key again, in case the fromClient() fails.

        # check for any input; Render input-form again when incomplete.
        if not skel.fromClient(kwargs) or not current_request.isPostRequest:
            return self._user_module.render.edit(
                skel=skel,
                tpl=self.passwordRecoveryStep3Template,
            )

        # validate security key
        if not securitykey.validate(skey):
            raise errors.PreconditionFailed()

        if not (recovery_request := securitykey.validate(recovery_key, session_bound=False)):
            raise errors.PreconditionFailed(
                i18n.translate(
                    key="viur.modules.user.passwordrecovery.keyexpired",
                    defaultText="The recovery key is expired or invalid. Please start the recovery process again.",
                    hint="Shown when the user needs more than 15 minutes to paste the key, or entered an invalid key."
                )
            )

        self.passwordRecoveryRateLimit.decrementQuota()

        # If we made it here, the key was correct, so we'd hopefully have a valid user for this
        user_skel = self._user_module.viewSkel().all().filter("name.idx =", recovery_request["user_name"]).getSkel()

        if not user_skel:
            raise errors.NotFound(
                i18n.translate(
                    key="viur.modules.user.passwordrecovery.usernotfound",
                    defaultText="There is no account with this name",
                    hint="We cant find an account with that name (Should never happen)"
                )
            )

        if user_skel["status"] != Status.ACTIVE:  # The account is locked or not yet validated. Abort the process.
            raise errors.NotFound(
                i18n.translate(
                    key="viur.modules.user.passwordrecovery.accountlocked",
                    defaultText="This account is currently locked. You cannot change it's password.",
                    hint="Attempted password recovery on a locked account"
                )
            )

        # Update the password, save the user, reset his session and show the success-template
        user_skel["password"] = skel["password"]
        user_skel.toDB(update_relations=False)

        return self._user_module.render.view(
            None,
            tpl=self.passwordRecoverySuccessTemplate,
        )

    @tasks.CallDeferred
    def sendUserPasswordRecoveryCode(self, user_name: str, recovery_key: str, user_agent: str) -> None:
        """
            Sends the given recovery code to the user given in userName. This function runs deferred
            so there's no timing sidechannel that leaks if this user exists. Per default, we'll send the
            code by email (assuming we have working email delivery), but this can be overridden to send it
            by SMS or other means. We'll also update the changedate for this user, so no more than one code
            can be send to any given user in four hours.
        """
        if user_skel := self._user_module.viewSkel().all().filter("name.idx =", user_name).getSkel():
            user_agent = user_agents.parse(user_agent)
            email.sendEMail(
                tpl=self.passwordRecoveryMail,
                skel=user_skel,
                dests=[user_name],
                recovery_key=recovery_key,
                user_agent={
                    "device": user_agent.get_device(),
                    "os": user_agent.get_os(),
                    "browser": user_agent.get_browser()
                }
            )

    @exposed
    @skey(forward_payload="data", session_bound=False)
    def verify(self, data):
        def transact(key):
            skel = self._user_module.editSkel()
            if not key or not skel.fromDB(key):
                return None
            skel["status"] = Status.WAITING_FOR_ADMIN_VERIFICATION \
                if self.registrationAdminVerificationRequired else Status.ACTIVE

            skel.toDB(update_relations=False)
            return skel

        if not isinstance(data, dict) or not (skel := db.RunInTransaction(transact, data.get("user_key"))):
            return self._user_module.render.view(None, tpl=self.verifyFailedTemplate)

        return self._user_module.render.view(skel, tpl=self.verifySuccessTemplate)

    def canAdd(self) -> bool:
        return self.registrationEnabled

    def addSkel(self):
        """
            Prepare the add-Skel for rendering.
            Currently only calls self._user_module.addSkel() and sets skel["status"] depending on
            self.registrationEmailVerificationRequired and self.registrationAdminVerificationRequired
            :return: viur.core.skeleton.Skeleton
        """
        skel = self._user_module.addSkel()

        if self.registrationEmailVerificationRequired:
            defaultStatusValue = Status.WAITING_FOR_EMAIL_VERIFICATION
        elif self.registrationAdminVerificationRequired:
            defaultStatusValue = Status.WAITING_FOR_ADMIN_VERIFICATION
        else:  # No further verification required
            defaultStatusValue = Status.ACTIVE

        skel.status.readOnly = True
        skel["status"] = defaultStatusValue

        if "password" in skel:
            skel.password.required = True  # The user will have to set a password

        return skel

    @force_ssl
    @exposed
    @skey(allow_empty=True)
    def add(self, *args, **kwargs):
        """
            Allows guests to register a new account if self.registrationEnabled is set to true

            .. seealso:: :func:`addSkel`, :func:`onAdded`, :func:`canAdd`, :func:`onAdd`

            :returns: The rendered, added object of the entry, eventually with error hints.

            :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
            :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        if not self.canAdd():
            raise errors.Unauthorized()
        skel = self.addSkel()
        if (
            not kwargs  # no data supplied
            or not current.request.get().isPostRequest  # bail out if not using POST-method
            or not skel.fromClient(kwargs)  # failure on reading into the bones
            or utils.parse.bool(kwargs.get("bounce"))  # review before adding
        ):
            # render the skeleton in the version it could as far as it could be read.
            return self._user_module.render.add(skel)
        self._user_module.onAdd(skel)
        skel.toDB()
        if self.registrationEmailVerificationRequired and skel["status"] == Status.WAITING_FOR_EMAIL_VERIFICATION:
            # The user will have to verify his email-address. Create a skey and send it to his address
            skey = securitykey.create(duration=datetime.timedelta(days=7), session_bound=False,
                                      user_key=utils.normalizeKey(skel["key"]),
                                      name=skel["name"])
            skel.skey = BaseBone(descr="Skey")
            skel["skey"] = skey
            email.sendEMail(dests=[skel["name"]], tpl=self._user_module.verifyEmailAddressMail, skel=skel)
        self._user_module.onAdded(skel)  # Call onAdded on our parent user module
        return self._user_module.render.addSuccess(skel)


class GoogleAccount(UserPrimaryAuthentication):
    METHOD_NAME = "X-VIUR-AUTH-Google-Account"

    @classmethod
    def patch_user_skel(cls, skel_cls):
        """
        Modifies the UserSkel to be equipped by a bones required by Google Auth
        """
        skel_cls.uid = StringBone(
            descr="Google UserID",
            required=False,
            readOnly=True,
            unique=UniqueValue(UniqueLockMethod.SameValue, False, "UID already in use"),
            params={
                "category": "Authentication",
            }
        )

        skel_cls.sync = BooleanBone(
            descr="Sync user data with OAuth-based services",
            defaultValue=True,
            params={
                "category": "Authentication",
                "tooltip":
                    "If set, user data like firstname and lastname is automatically kept"
                    "synchronous with the information stored at the OAuth service provider"
                    "(e.g. Google Login)."
            }
        )

    @exposed
    @force_ssl
    @skey(allow_empty=True)
    def login(self, token: str | None = None, *args, **kwargs):
        # FIXME: Check if already logged in
        if not conf.user.google_client_id:
            raise errors.PreconditionFailed("Please configure conf.user.google_client_id!")

        if not token:
            request = current.request.get()
            request.response.headers["Content-Type"] = "text/html"
            if request.response.headers.get("cross-origin-opener-policy") == "same-origin":
                # We have to allow popups here
                request.response.headers["cross-origin-opener-policy"] = "same-origin-allow-popups"

            file_path = conf.instance.core_base_path.joinpath("viur/core/template/vi_user_google_login.html")
            with open(file_path) as file:
                tpl_string = file.read()

            # FIXME: Use Jinja2 for rendering?
            tpl_string = tpl_string.replace("{{ clientID }}", conf.user.google_client_id)
            extendCsp({
                "script-src": ["sha256-JpzaUIxV/gVOQhKoDLerccwqDDIVsdn1JclA6kRNkLw="],
                "style-src": ["sha256-FQpGSicYMVC5jxKGS5sIEzrRjSJmkxKPaetUc7eamqc="]
            })
            return tpl_string

        user_info = id_token.verify_oauth2_token(token, requests.Request(), conf.user.google_client_id)
        if user_info["iss"] not in {"accounts.google.com", "https://accounts.google.com"}:
            raise ValueError("Invalid issuer")

        # Token looks valid :)
        uid = user_info["sub"]
        email = user_info["email"]

        base_skel = self._user_module.baseSkel()
        update = False
        if not (user_skel := base_skel.all().filter("uid =", uid).getSkel()):
            # We'll try again - checking if there's already an user with that email
            if not (user_skel := base_skel.all().filter("name.idx =", email.lower()).getSkel()):
                # Still no luck - it's a completely new user
                if not self.registrationEnabled:
                    if (domain := user_info.get("hd")) and domain in conf.user.google_gsuite_domains:
                        logging.debug(f"Google user is from allowed {domain} - adding account")
                    else:
                        logging.debug(f"Google user is from {domain} - denying registration")
                        raise errors.Forbidden("Registration for new users is disabled")

                user_skel = base_skel
                user_skel["uid"] = uid
                user_skel["name"] = email
                update = True

        # Take user information from Google, if wanted!
        if user_skel["sync"]:
            for target, source in {
                "name": email,
                "firstname": user_info.get("given_name"),
                "lastname": user_info.get("family_name"),
            }.items():

                if user_skel[target] != source:
                    user_skel[target] = source
                    update = True

        if update:
            assert user_skel.toDB()

        return self.next_or_finish(user_skel)


class UserSecondFactorAuthentication(UserAuthentication, abc.ABC):
    """Abstract class for all second factors."""
    MAX_RETRY = 3
    second_factor_login_template = "user_login_secondfactor"
    """Template to enter the TOPT on login"""

    @property
    @abc.abstractmethod
    def NAME(self) -> str:
        """Name for this factor for templates."""
        ...

    @property
    @abc.abstractmethod
    def ACTION_NAME(self) -> str:
        """The action name for this factor, used as path-segment."""
        ...

    def __init__(self, moduleName, modulePath, _user_module):
        super().__init__(moduleName, modulePath, _user_module)
        self.action_url = f"{self.modulePath}/{self.ACTION_NAME}"
        self.add_url = f"{self.modulePath}/add"
        self.start_url = f"{self.modulePath}/start"


class TimeBasedOTP(UserSecondFactorAuthentication):
    METHOD_NAME = "X-VIUR-2FACTOR-TimeBasedOTP"
    WINDOW_SIZE = 5
    ACTION_NAME = "otp"
    NAME = "Time based Otp"
    second_factor_login_template = "user_login_secondfactor"

    @dataclasses.dataclass
    class OtpConfig:
        """
        This dataclass is used to provide an interface for a OTP token
        algorithm description that is passed within the TimeBasedOTP
        class for configuration.
        """
        secret: str
        timedrift: float = 0.0
        algorithm: t.Literal["sha1", "sha256"] = "sha1"
        interval: int = 60

    class OtpSkel(skeleton.RelSkel):
        """
        This is the Skeleton used to ask for the OTP token.
        """
        otptoken = NumericBone(
            descr="Token",
            required=True,
            max=999999,
            min=0,
        )

    @classmethod
    def patch_user_skel(cls, skel_cls):
        """
        Modifies the UserSkel to be equipped by a bones required by Timebased OTP
        """
        # One-Time Password Verification
        skel_cls.otp_serial = StringBone(
            descr="OTP serial",
            searchable=True,
            params={
                "category": "Second Factor Authentication",
            }
        )

        skel_cls.otp_secret = CredentialBone(
            descr="OTP secret",
            params={
                "category": "Second Factor Authentication",
            }
        )

        skel_cls.otp_timedrift = NumericBone(
            descr="OTP time drift",
            readOnly=True,
            defaultValue=0,
            params={
                "category": "Second Factor Authentication",
            }
        )

    def get_config(self, skel: skeleton.SkeletonInstance) -> OtpConfig | None:
        """
        Returns an instance of self.OtpConfig with a provided token configuration,
        or None when there is no appropriate configuration of this second factor handler available.
        """

        if otp_secret := skel.dbEntity.get("otp_secret"):
            return self.OtpConfig(secret=otp_secret, timedrift=skel.dbEntity.get("otp_timedrift") or 0)

        return None

    def can_handle(self, skel: skeleton.SkeletonInstance) -> bool:
        """
        Specified whether the second factor authentication can be handled by the given user or not.
        """
        return bool(self.get_config(skel))

    @exposed
    def start(self):
        """
        Configures OTP login for the current session.

        A special otp_user_conf has to be specified as a dict, which is stored into the session.
        """
        session = current.session.get()

        if not (user_key := session.get("possible_user_key")):
            raise errors.PreconditionFailed(
                "Second factor can only be triggered after successful primary authentication."
            )

        user_skel = self._user_module.baseSkel()
        if not user_skel.fromDB(user_key):
            raise errors.NotFound("The previously authenticated user is gone.")

        if not (otp_user_conf := self.get_config(user_skel)):
            raise errors.PreconditionFailed("This second factor is not available for the user")

        otp_user_conf = {
            "key": str(user_key),
        } | dataclasses.asdict(otp_user_conf)

        session = current.session.get()
        session["_otp_user"] = otp_user_conf
        session.markChanged()

        return self._user_module.render.edit(
            self.OtpSkel(),
            params={
                "name": i18n.translate(self.NAME),
                "action_name": self.ACTION_NAME,
                "action_url": f"{self.modulePath}/{self.ACTION_NAME}",
            },
            tpl=self.second_factor_login_template
        )

    @exposed
    @force_ssl
    @skey(allow_empty=True)
    def otp(self, *args, **kwargs):
        """
        Performs the second factor validation and interaction with the client.
        """
        session = current.session.get()
        if not (otp_user_conf := session.get("_otp_user")):
            raise errors.PreconditionFailed("No OTP process started in this session")

        # Check if maximum second factor verification attempts
        if (attempts := otp_user_conf.get("attempts") or 0) > self.MAX_RETRY:
            raise errors.Forbidden("Maximum amount of authentication retries exceeded")

        # Read the OTP token via the skeleton, to obtain a valid value
        skel = self.OtpSkel()
        if skel.fromClient(kwargs):
            # Verify the otptoken. If valid, this returns the current timedrift index for this hardware OTP.
            res = self.verify(
                otp=skel["otptoken"],
                secret=otp_user_conf["secret"],
                algorithm=otp_user_conf.get("algorithm") or "sha1",
                interval=otp_user_conf.get("interval") or 60,
                timedrift=otp_user_conf.get("timedrift") or 0.0,
                valid_window=self.WINDOW_SIZE
            )
        else:
            res = None

        # Check if Token is invalid. Caution: 'if not verifyIndex' gets false positive for verifyIndex === 0!
        if res is None:
            otp_user_conf["attempts"] = attempts + 1
            session.markChanged()
            skel.errors = [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Wrong OTP Token", ["otptoken"])]
            return self._user_module.render.edit(
                skel,
                name=i18n.translate(self.NAME),
                action_name=self.ACTION_NAME,
                action_url=f"{self.modulePath}/{self.ACTION_NAME}",
                tpl=self.second_factor_login_template
            )

        # Remove otp user config from session
        user_key = db.keyHelper(otp_user_conf["key"], self._user_module._resolveSkelCls().kindName)
        del session["_otp_user"]
        session.markChanged()

        # Check if the OTP device has a time drift

        timedriftchange = float(res) - otp_user_conf["timedrift"]
        if abs(timedriftchange) > 2:
            # The time-drift change accumulates to more than 2 minutes (for interval==60):
            # update clock-drift value accordingly
            self.updateTimeDrift(user_key, timedriftchange)

        # Continue with authentication
        return self._user_module.secondFactorSucceeded(self, user_key)

    @staticmethod
    def verify(
        otp: str | int,
        secret: str,
        algorithm: str = "sha1",
        interval: int = 60,
        timedrift: float = 0.0,
        for_time: datetime.datetime | None = None,
        valid_window: int = 0,
    ) -> int | None:
        """
        Verifies the OTP passed in against the current time OTP.

        This is a fork of pyotp.verify. Rather than true/false, if valid_window > 0, it returns the index for which
        the OTP value obtained by pyotp.at(for_time=time.time(), counter_offset=index) equals the current value shown
        on the hardware token generator. This can be used to store the time drift of a given token generator.

        :param otp: the OTP token to check against
        :param secret: The OTP secret
        :param algorithm: digest function to use in the HMAC (expected to be sha1 or sha256)
        :param interval: the time interval in seconds for OTP. This defaults to 60 (old OTP c200 Generators). In
        pyotp, default is 30!
        :param timedrift: The known timedrift (old index) of the hardware OTP generator
        :param for_time: Time to check OTP at (defaults to now)
        :param valid_window: extends the validity to this many counter ticks before and after the current one
        :returns: The index where verification succeeded, None otherwise
        """
        # get the hashing digest
        digest = {
            "sha1": hashlib.sha1,
            "sha256": hashlib.sha256,
        }.get(algorithm)

        if not digest:
            raise errors.NotImplemented(f"{algorithm=} is not implemented")

        if for_time is None:
            for_time = datetime.datetime.now()

        # Timedrift is updated only in fractions in order to prevent problems, but we need an integer index
        timedrift = round(timedrift)
        secret = bytes.decode(base64.b32encode(bytes.fromhex(secret)))  # decode secret
        otp = str(otp).zfill(6)  # fill with zeros in front

        # logging.debug(f"TimeBasedOTP:verify: {digest=}, {interval=}, {valid_window=}")
        totp = pyotp.TOTP(secret, digest=digest, interval=interval)

        if valid_window:
            for offset in range(timedrift - valid_window, timedrift + valid_window + 1):
                token = str(totp.at(for_time, offset))
                # logging.debug(f"TimeBasedOTP:verify: {offset=}, {otp=}, {token=}")
                if hmac.compare_digest(otp, token):
                    return offset

            return None

        return 0 if hmac.compare_digest(otp, str(totp.at(for_time, timedrift))) else None

    def updateTimeDrift(self, user_key: db.Key, idx: float) -> None:
        """
            Updates the clock-drift value.
            The value is only changed in 1/10 steps, so that a late submit by an user doesn't skew
            it out of bounds. Maximum change per call is 0.3 minutes.
            :param user_key: For which user should the update occour
            :param idx: How many steps before/behind was that token
            :return:
        """

        # FIXME: The callback in viur-core must be improved, to accept user_skel

        def transaction(user_key, idx):
            user = db.Get(user_key)
            if not isinstance(user.get("otp_timedrift"), float):
                user["otp_timedrift"] = 0.0
            user["otp_timedrift"] += min(max(0.1 * idx, -0.3), 0.3)
            db.Put(user)

        db.RunInTransaction(transaction, user_key, idx)


class AuthenticatorOTP(UserSecondFactorAuthentication):
    """
    This class handles the second factor for apps like authy and so on
    """
    METHOD_NAME = "X-VIUR-2FACTOR-AuthenticatorOTP"

    second_factor_add_template = "user_secondfactor_add"
    """Template to configure (add) a new TOPT"""

    ACTION_NAME = "authenticator_otp"
    """Action name provided for *otp_template* on login"""

    NAME = "Authenticator App"

    @exposed
    @force_ssl
    @skey(allow_empty=True)
    def add(self, otp=None):
        """
        We try to read the otp_app_secret form the current session. When this fails we generate a new one and store
        it in the session.

        If an otp and a skey are provided we are validate the skey and the otp. If both is successfully we store
        the otp_app_secret from the session in the user entry.
        """
        current_session = current.session.get()

        if not (otp_app_secret := current_session.get("_maybe_otp_app_secret")):
            otp_app_secret = AuthenticatorOTP.generate_otp_app_secret()
            current_session["_maybe_otp_app_secret"] = otp_app_secret
            current_session.markChanged()

        if otp is None:
            return self._user_module.render.second_factor_add(
                tpl=self.second_factor_add_template,
                action_name=self.ACTION_NAME,
                name=i18n.translate(self.NAME),
                add_url=self.add_url,
                otp_uri=AuthenticatorOTP.generate_otp_app_secret_uri(otp_app_secret))
        else:
            if not AuthenticatorOTP.verify_otp(otp, otp_app_secret):
                return self._user_module.render.second_factor_add(
                    tpl=self.second_factor_add_template,
                    action_name=self.ACTION_NAME,
                    name=i18n.translate(self.NAME),
                    add_url=self.add_url,
                    otp_uri=AuthenticatorOTP.generate_otp_app_secret_uri(otp_app_secret))  # to add errors

            # Now we can set the otp_app_secret to the current User and render der Success-template
            AuthenticatorOTP.set_otp_app_secret(otp_app_secret)
            return self._user_module.render.second_factor_add_success(
                action_name=self.ACTION_NAME,
                name=i18n.translate(self.NAME),
            )

    def can_handle(self, skel: skeleton.SkeletonInstance) -> bool:
        """
        We can only handle the second factor if we have stored an otp_app_secret before.
        """
        return bool(skel.dbEntity.get("otp_app_secret", ""))

    @classmethod
    def patch_user_skel(cls, skel_cls):
        """
        Modifies the UserSkel to be equipped by bones required by Authenticator App
        """
        # Authenticator OTP Apps (like Authy)
        skel_cls.otp_app_secret = CredentialBone(
            descr="OTP Secret (App-Key)",
            params={
                "category": "Second Factor Authentication",
            }
        )

    @classmethod
    def set_otp_app_secret(cls, otp_app_secret=None):
        """
        Write a new OTP Token in the current user entry.
        """
        if otp_app_secret is None:
            logging.error("No 'otp_app_secret' is provided")
            raise errors.PreconditionFailed("No 'otp_app_secret' is provided")
        if not (cuser := current.user.get()):
            raise errors.Unauthorized()

        def transaction(user_key):
            if not (user := db.Get(user_key)):
                raise errors.NotFound()
            user["otp_app_secret"] = otp_app_secret
            db.Put(user)

        db.RunInTransaction(transaction, cuser["key"])

    @classmethod
    def generate_otp_app_secret_uri(cls, otp_app_secret) -> str:
        """
        :return an otp uri like otpauth://totp/Example:alice@google.com?secret=ABCDEFGH1234&issuer=Example
        """
        if not (cuser := current.user.get()):
            raise errors.Unauthorized()
        if not (issuer := conf.user.otp_issuer):
            logging.warning(
                f"conf.user.otp_issuer is None we replace the issuer by {conf.instance.project_id=}")
            issuer = conf.instance.project_id

        return pyotp.TOTP(otp_app_secret).provisioning_uri(name=cuser["name"], issuer_name=issuer)

    @classmethod
    def generate_otp_app_secret(cls) -> str:
        """
        Generate a new OTP Secret
        :return an otp
        """
        return pyotp.random_base32()

    @classmethod
    def verify_otp(cls, otp: str | int, secret: str) -> bool:
        return pyotp.TOTP(secret).verify(otp)

    @exposed
    def start(self):
        otp_user_conf = {"attempts": 0}
        session = current.session.get()
        session["_otp_user"] = otp_user_conf
        session.markChanged()
        return self._user_module.render.edit(
            TimeBasedOTP.OtpSkel(),
            params={
                "name": i18n.translate(self.NAME),
                "action_name": self.ACTION_NAME,
                "action_url": self.action_url,
            },
            tpl=self.second_factor_login_template,
        )

    @exposed
    @force_ssl
    @skey
    def authenticator_otp(self, **kwargs):
        """
        We verify the otp here with the secret we stored before.
        """
        session = current.session.get()
        user_key = db.Key(self._user_module.kindName, session["possible_user_key"])

        if not (otp_user_conf := session.get("_otp_user")):
            raise errors.PreconditionFailed("No OTP process started in this session")

        # Check if maximum second factor verification attempts
        if (attempts := otp_user_conf.get("attempts") or 0) > self.MAX_RETRY:
            raise errors.Forbidden("Maximum amount of authentication retries exceeded")

        if not (user := db.Get(user_key)):
            raise errors.NotFound()

        skel = TimeBasedOTP.OtpSkel()
        if not skel.fromClient(kwargs):
            raise errors.PreconditionFailed()
        otp_token = str(skel["otptoken"]).zfill(6)

        if AuthenticatorOTP.verify_otp(otp=otp_token, secret=user["otp_app_secret"]):
            return self._user_module.secondFactorSucceeded(self, user_key)
        otp_user_conf["attempts"] = attempts + 1
        session.markChanged()
        skel.errors = [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Wrong OTP Token", ["otptoken"])]
        return self._user_module.render.edit(
            skel,
            name=i18n.translate(self.NAME),
            action_name=self.ACTION_NAME,
            action_url=self.action_url,
            tpl=self.second_factor_login_template,
        )


class User(List):
    kindName = "user"
    addTemplate = "user_add"
    addSuccessTemplate = "user_add_success"
    lostPasswordTemplate = "user_lostpassword"
    verifyEmailAddressMail = "user_verify_address"
    passwordRecoveryMail = "user_password_recovery"

    authenticationProviders: t.Iterable[UserPrimaryAuthentication] = tuple(filter(
        None, (
            UserPassword,
            conf.user.google_client_id and GoogleAccount,
        )
    ))
    """
    Specifies primary authentication providers that are made available
    as sub-modules under `user/auth_<classname>`. They might require
    customization or configuration.
    """

    secondFactorProviders: t.Iterable[UserSecondFactorAuthentication] = (
        TimeBasedOTP,
        AuthenticatorOTP,
    )
    """
    Specifies secondary authentication providers that are made available
    as sub-modules under `user/f2_<classname>`. They might require
    customization or configuration, which is determined during the
    login-process depending on the user that wants to login.
    """

    validAuthenticationMethods = tuple(filter(
        None, (
            (UserPassword, AuthenticatorOTP),
            (UserPassword, TimeBasedOTP),
            (UserPassword, None),
            (GoogleAccount, None) if conf.user.google_client_id else None,
        )
    ))
    """
    Specifies the possible combinations of primary- and secondary factor
    login methos.

    GoogleLogin defaults to no second factor, as the Google Account can be
    secured by a secondary factor. AuthenticatorOTP and TimeBasedOTP are only
    handled when there is a user-dependent configuration available.
    """

    msg_missing_second_factor = "Second factor required but not configured for this user."

    secondFactorTimeWindow = datetime.timedelta(minutes=10)

    default_order = "name.idx"

    adminInfo = {
        "icon": "person-fill",
        "actions": [
            "trigger_kick",
            "trigger_takeover",
        ],
        "customActions": {
            "trigger_kick": {
                "name": i18n.translate(
                    key="viur.modules.user.customActions.kick",
                    defaultText="Kick user",
                    hint="Title of the kick user function"
                ),
                "icon": "trash2-fill",
                "access": ["root"],
                "action": "fetch",
                "url": "/vi/{{module}}/trigger/kick/{{key}}?skey={{skey}}",
                "confirm": i18n.translate(
                    key="viur.modules.user.customActions.kick.confirm",
                    defaultText="Do you really want to drop all sessions of the selected user from the system?",
                ),
                "success": i18n.translate(
                    key="viur.modules.user.customActions.kick.success",
                    defaultText="Sessions of the user are being invalidated.",
                ),
            },
            "trigger_takeover": {
                "name": i18n.translate(
                    key="viur.modules.user.customActions.takeover",
                    defaultText="Take-over user",
                    hint="Title of the take user over function"
                ),
                "icon": "file-person-fill",
                "access": ["root"],
                "action": "fetch",
                "url": "/vi/{{module}}/trigger/takeover/{{key}}?skey={{skey}}",
                "confirm": i18n.translate(
                    key="viur.modules.user.customActions.takeover.confirm",
                    defaultText="Do you really want to replace your current user session by a "
                                "user session of the selected user?",
                ),
                "success": i18n.translate(
                    key="viur.modules.user.customActions.takeover.success",
                    defaultText="You're now know as the selected user!",
                ),
                "then": "reload-vi",
            },
        },
    }

    roles = {
        "admin": "*",
    }

    def __init__(self, moduleName, modulePath):
        for provider in self.authenticationProviders:
            assert issubclass(provider, UserPrimaryAuthentication)
            name = f"auth_{provider.__name__.lower()}"
            setattr(self, name, provider(name, f"{modulePath}/{name}", self))

        for provider in self.secondFactorProviders:
            assert issubclass(provider, UserSecondFactorAuthentication)
            name = f"f2_{provider.__name__.lower()}"
            setattr(self, name, provider(name, f"{modulePath}/{name}", self))

        super().__init__(moduleName, modulePath)

    def get_role_defaults(self, role: str) -> set[str]:
        """
        Returns a set of default access rights for a given role.
        """
        if role in ("viewer", "editor", "admin"):
            return {"admin"}

        return set()

    def addSkel(self):
        skel = super().addSkel().clone()
        user = current.user.get()
        if not (user and user["access"] and (f"{self.moduleName}-add" in user["access"] or "root" in user["access"])):
            skel.status.readOnly = True
            skel["status"] = Status.UNSET
            skel.status.visible = False
            skel.access.readOnly = True
            skel["access"] = []
            skel.access.visible = False
        else:
            # An admin tries to add a new user.
            skel.status.readOnly = False
            skel.status.visible = True
            skel.access.readOnly = False
            skel.access.visible = True

        if "password" in skel:
            # Unlock and require a password
            skel.password.required = True
            skel.password.visible = True
            skel.password.readOnly = False

        skel.name.readOnly = False  # Don't enforce readonly name in user/add
        return skel

    def editSkel(self, *args, **kwargs):
        skel = super().editSkel().clone()

        if "password" in skel:
            skel.password.required = False
            skel.password.visible = True
            skel.password.readOnly = False

        user = current.user.get()

        lockFields = not (user and "root" in user["access"])  # If we aren't root, make certain fields read-only
        skel.name.readOnly = lockFields
        skel.access.readOnly = lockFields
        skel.status.readOnly = lockFields

        return skel

    def secondFactorProviderByClass(self, cls) -> UserSecondFactorAuthentication:
        return getattr(self, f"f2_{cls.__name__.lower()}")

    def getCurrentUser(self):
        session = current.session.get()

        if session and (user := session.get("user")):
            skel = self.baseSkel()
            skel.setEntity(user)
            return skel

        return None

    def continueAuthenticationFlow(self, provider: UserPrimaryAuthentication, user_key: db.Key):
        """
        Continue authentication flow when primary authentication succeeded.
        """
        skel = self.baseSkel()

        if not skel.fromDB(user_key):
            raise errors.NotFound("User was not found.")

        if not provider.can_handle(skel):
            raise errors.Forbidden("User is not allowed to use this primary login method.")

        session = current.session.get()
        session["possible_user_key"] = user_key.id_or_name
        session["_secondFactorStart"] = utils.utcNow()
        session.markChanged()

        second_factor_providers = []

        for auth_provider, second_factor in self.validAuthenticationMethods:
            if isinstance(provider, auth_provider):
                if second_factor is not None:
                    second_factor_provider_instance = self.secondFactorProviderByClass(second_factor)
                    if second_factor_provider_instance.can_handle(skel):
                        second_factor_providers.append(second_factor_provider_instance)
                else:
                    second_factor_providers.append(None)

        if len(second_factor_providers) > 1 and None in second_factor_providers:
            # We have a second factor. So we can get rid of the None
            second_factor_providers.pop(second_factor_providers.index(None))

        if len(second_factor_providers) == 0:
            raise errors.NotAcceptable(self.msg_missing_second_factor)
        elif len(second_factor_providers) == 1:
            if second_factor_providers[0] is None:
                # We allow sign-in without a second factor
                return self.authenticateUser(user_key)
            # We have only one second factor we don't need the choice template
            return second_factor_providers[0].start(user_key)

        # In case there is more than one second factor, let the user select a method.
        return self.render.second_factor_choice(second_factors=second_factor_providers)

    def secondFactorSucceeded(self, provider: UserSecondFactorAuthentication, user_key: db.Key):
        """
        Continue authentication flow when secondary authentication succeeded.
        """
        session = current.session.get()
        if session["possible_user_key"] != user_key.id_or_name:
            raise errors.Forbidden()

        # Assert that the second factor verification finished in time
        if utils.utcNow() - session["_secondFactorStart"] > self.secondFactorTimeWindow:
            raise errors.RequestTimeout()

        return self.authenticateUser(user_key)

    def authenticateUser(self, key: db.Key, **kwargs):
        """
            Performs Log-In for the current session and the given user key.

            This resets the current session: All fields not explicitly marked as persistent
            by conf.user.session_persistent_fields_on_login are gone afterwards.

            :param key: The (DB-)Key of the user we shall authenticate
        """
        skel = self.baseSkel()
        if not skel.fromDB(key):
            raise ValueError(f"Unable to authenticate unknown user {key}")

        # Verify that this user account is active
        if skel["status"] < Status.ACTIVE.value:
            raise errors.Forbidden("The user is disabled and cannot be authenticated.")

        # Update session for user
        session = current.session.get()
        # Remember persistent fields...
        take_over = {k: v for k, v in session.items() if k in conf.user.session_persistent_fields_on_login}
        session.reset()
        # and copy them over to the new session
        session |= take_over

        # Update session, user and request
        session["user"] = skel.dbEntity

        current.request.get().response.headers[securitykey.SECURITYKEY_STATIC_HEADER] = session.static_security_key
        current.user.set(self.getCurrentUser())

        self.onLogin(skel)

        return self.render.loginSucceeded(**kwargs)

    @exposed
    @skey
    def logout(self, *args, **kwargs):
        """
            Implements the logout action. It also terminates the current session (all keys not listed
            in viur.session_persistent_fields_on_logout will be lost).
        """
        if not (user := current.user.get()):
            raise errors.Unauthorized()

        self.onLogout(user)

        session = current.session.get()
        take_over = {k: v for k, v in session.items() if k in conf.user.session_persistent_fields_on_logout}
        session.reset()
        session |= take_over
        current.user.set(None)  # set user to none in context var
        return self.render.logoutSuccess()

    @exposed
    def login(self, *args, **kwargs):
        return self.render.loginChoices([
            (primary.METHOD_NAME, secondary.METHOD_NAME if secondary else None)
            for primary, secondary in self.validAuthenticationMethods
        ])

    def onLogin(self, skel: skeleton.SkeletonInstance):
        """
        Hook to be called on user login.
        """
        # Update the lastlogin timestamp (if available!)
        if "lastlogin" in skel:
            now = utils.utcNow()

            # Conserve DB-Writes: Update the user max once in 30 Minutes (why??)
            if not skel["lastlogin"] or ((now - skel["lastlogin"]) > datetime.timedelta(minutes=30)):
                skel["lastlogin"] = now
                skel.toDB(update_relations=False)

        logging.info(f"""User {skel["name"]} logged in""")

    def onLogout(self, skel: skeleton.SkeletonInstance):
        """
        Hook to be called on user logout.
        """
        logging.info(f"""User {skel["name"]} logged out""")

    @exposed
    def view(self, key: db.Key | int | str = "self", *args, **kwargs):
        """
            Allow a special key "self" to reference the current user.

            By default, any authenticated user can view its own user entry,
            to obtain access rights and any specific user information.
            This behavior is defined in the customized `canView` function,
            which is overwritten by the User-module.

            The rendered skeleton can be modified or restriced by specifying
            a customized view-skeleton.
        """
        if key == "self":
            if user := current.user.get():
                key = user["key"]
            else:
                raise errors.Unauthorized("Cannot view 'self' with unknown user")

        return super().view(key, *args, **kwargs)

    def canView(self, skel) -> bool:
        if user := current.user.get():
            if skel["key"] == user["key"]:
                return True

            if "root" in user["access"] or "user-view" in user["access"]:
                return True

        return False

    @exposed
    @skey(allow_empty=True)
    def edit(self, key: db.Key | int | str = "self", *args, **kwargs):
        """
            Allow a special key "self" to reference the current user.

            This modification will only allow to use "self" as a key;
            The specific access right to let the user edit itself must
            still be customized.

            The rendered and editable skeleton can be modified or restriced
            by specifying a customized edit-skeleton.
        """
        if key == "self":
            if user := current.user.get():
                key = user["key"]
            else:
                raise errors.Unauthorized("Cannot edit 'self' with unknown user")

        return super().edit(key, *args, **kwargs)

    @exposed
    def getAuthMethods(self, *args, **kwargs):
        """Inform tools like Viur-Admin which authentication to use"""
        # FIXME: This is almost the same code as in index()...
        # FIXME: VIUR4: The entire function should be removed!
        # TODO: Align result with index(), so that primary and secondary login is presented.
        # logging.warning("DEPRECATED!!! Use of 'User.getAuthMethods' is deprecated! Use 'User.login'-method instead!")

        res = [
            (primary.METHOD_NAME, secondary.METHOD_NAME if secondary else None)
            for primary, secondary in self.validAuthenticationMethods
        ]

        return json.dumps(res)

    @exposed
    @skey
    def trigger(self, action: str, key: str):
        current.request.get().response.headers["Content-Type"] = "application/json"

        # Check for provided access right definition (equivalent to client-side check), fallback to root!
        access = self.adminInfo.get("customActions", {}).get(f"trigger_{action}", {}).get("access") or ("root", )
        if not ((cuser := current.user.get()) and any(role in cuser["access"] for role in access)):
            raise errors.Unauthorized()

        skel = self.baseSkel()
        if not skel.fromDB(key):
            raise errors.NotFound()

        match action:
            case "takeover":
                self.authenticateUser(skel["key"])

            case "kick":
                session.killSessionByUser(skel["key"])

            case _:
                raise errors.NotImplemented(f"Action {action!r} not implemented")

        return json.dumps("OKAY")

    def onEdited(self, skel):
        super().onEdited(skel)
        # In case the user is set to inactive, kill all sessions
        if "status" in skel and skel["status"] < Status.ACTIVE.value:
            session.killSessionByUser(skel["key"])

    def onDeleted(self, skel):
        super().onDeleted(skel)
        # Invalidate all sessions of that user
        session.killSessionByUser(skel["key"])


@tasks.StartupTask
def createNewUserIfNotExists():
    """
        Create a new Admin user, if the userDB is empty
    """
    if (
        (user_module := getattr(conf.main_app.vi, "user", None))
        and isinstance(user_module, User)
        and "addSkel" in dir(user_module)
        and "validAuthenticationMethods" in dir(user_module)
        # UserPassword must be one of the primary login methods
        and any(
            issubclass(provider[0], UserPassword)
            for provider in user_module.validAuthenticationMethods
        )
    ):
        if not db.Query(user_module.addSkel().kindName).getEntry():  # There's currently no user in the database
            addSkel = skeleton.skeletonByKind(user_module.addSkel().kindName)()  # Ensure we have the full skeleton
            uname = f"""admin@{conf.instance.project_id}.appspot.com"""
            pw = utils.string.random(13)
            addSkel["name"] = uname
            addSkel["status"] = Status.ACTIVE  # Ensure it's enabled right away
            addSkel["access"] = ["root"]
            addSkel["password"] = pw

            try:
                addSkel.toDB()
            except Exception as e:
                logging.critical(f"Something went wrong when trying to add admin user {uname!r} with Password {pw!r}")
                logging.exception(e)
                return

            msg = f"ViUR created a new admin-user for you!\nUsername: {uname}\nPassword: {pw}"

            logging.warning(msg)
            email.sendEMailToAdmins("New ViUR password", msg)


# DEPRECATED ATTRIBUTES HANDLING

def __getattr__(attr):
    match attr:
        case "userSkel":
            msg = f"Use of `userSkel` is deprecated; Please use `UserSkel` instead!"
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            logging.warning(msg)
            return UserSkel

    return super(__import__(__name__).__class__).__getattr__(attr)
