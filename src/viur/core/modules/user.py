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
import typing
from google.auth.transport import requests
from google.oauth2 import id_token

from viur.core import (
    conf, current, db, email, errors, i18n,
    securitykey, session, skeleton, tasks, utils, Module
)
from viur.core.decorators import *
from viur.core.bones import *
from viur.core.bones.password import PBKDF2_DEFAULT_ITERATIONS, encode_password
from viur.core.i18n import translate
from viur.core.prototypes.list import List
from viur.core.ratelimit import RateLimit
from viur.core.securityheaders import extendCsp
from viur.core.utils import parse_bool


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
    kindName = "user"
    # Properties required by google and custom auth
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

    # Properties required by custom auth
    password = PasswordBone(
        descr="Password",
        required=False,
        readOnly=True,
        visible=False,
    )

    # Properties required by google auth
    uid = StringBone(
        descr="Google's UserID",
        required=False,
        readOnly=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, False, "UID already in use"),
    )

    sync = BooleanBone(
        descr="Sync user data with OAuth-based services",
        defaultValue=True,
        params={
            "tooltip":
                "If set, user data like firstname and lastname is automatically kept synchronous with the information "
                "stored at the OAuth service provider (e.g. Google Login)."
        }
    )

    gaeadmin = BooleanBone(
        descr="Is GAE Admin",
        defaultValue=False,
        readOnly=True,
    )

    # Generic properties

    roles = SelectBone(
        descr=i18n.translate("viur.user.bone.roles", defaultText="Roles"),
        values=conf["viur.user.roles"],
        required=True,
        multiple=True,
        # fixme: This is generally broken in VIUR! See #776 for details.
        # vfunc=lambda values:
        #     i18n.translate(
        #         "user.bone.roles.invalid",
        #         defaultText="Invalid role setting: 'custom' can only be set alone.")
        #     if "custom" in values and len(values) > 1 else None,
        defaultValue=list(conf["viur.user.roles"].keys())[:1],
    )

    access = SelectBone(
        descr=i18n.translate("viur.user.bone.access", defaultText="Access rights"),
        values=lambda: {
            right: i18n.translate("server.modules.user.accessright.%s" % right, defaultText=right)
            for right in sorted(conf["viur.accessRights"])
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

    # One-Time Password Verification
    otp_serial = StringBone(
        descr="OTP serial",
        searchable=True,
    )

    otp_secret = CredentialBone(
        descr="OTP secret",
    )

    otp_timedrift = NumericBone(
        descr="OTP time drift",
        readOnly=True,
        defaultValue=0,
    )
    # Authenticator OTP Apps (like Authy)
    otp_app_secret = CredentialBone(
        descr="OTP Secret (App-Key)",

    )

    admin_config = JsonBone(  # This bone stores settings from the vi
        descr="Config for the User",
        visible=False
    )

    @classmethod
    def toDB(cls, skel, *args, **kwargs):
        # Roles
        if skel["roles"] and "custom" not in skel["roles"]:
            # Collect access rights through rules
            access = set()

            for role in skel["roles"]:
                # Get default access for this role
                access |= conf["viur.mainApp"].vi.user.get_role_defaults(role)

                # Go through all modules and evaluate available role-settings
                for name in dir(conf["viur.mainApp"].vi):
                    if name.startswith("_"):
                        continue

                    module = getattr(conf["viur.mainApp"].vi, name)
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

            skel["access"] = list(access)

        return super().toDB(skel, *args, **kwargs)


class UserAuthentication(Module):
    def __init__(self, moduleName, modulePath, userModule):
        super().__init__(moduleName, modulePath)
        self._user_module = userModule


class UserPassword(UserAuthentication):
    registrationEnabled = False
    registrationEmailVerificationRequired = True
    registrationAdminVerificationRequired = True

    verifySuccessTemplate = "user_verify_success"
    verifyEmailAddressMail = "user_verify_address"
    verifyFailedTemplate = "user_verify_failed"
    passwordRecoveryTemplate = "user_passwordrecover"
    passwordRecoveryMail = "user_password_recovery"
    passwordRecoveryAlreadySendTemplate = "user_passwordrecover_already_sent"
    passwordRecoverySuccessTemplate = "user_passwordrecover_success"
    passwordRecoveryInvalidTokenTemplate = "user_passwordrecover_invalid_token"
    passwordRecoveryInstructionsSentTemplate = "user_passwordrecover_mail_sent"
    passwordRecoveryStep1Template = "user_passwordrecover_step1"
    passwordRecoveryStep2Template = "user_passwordrecover_step2"
    passwordRecoveryFailedTemplate = "user_passwordrecover_failed"
    # The default rate-limit for password recovery (10 tries each 15 minutes)
    passwordRecoveryRateLimit = RateLimit("user.passwordrecovery", 10, 15, "ip")
    # Limit (invalid) login-retries to once per 5 seconds
    loginRateLimit = RateLimit("user.login", 12, 1, "ip")

    # Default translations for password recovery
    passwordRecoveryKeyExpired = i18n.translate(
        key="viur.modules.user.passwordrecovery.keyexpired",
        defaultText="The key is expired. Please try again",
        hint="Shown when the user needs more than 10 minutes to paste the key"
    )
    passwordRecoveryKeyInvalid = i18n.translate(
        key="viur.modules.user.passwordrecovery.keyinvalid",
        defaultText="The key is invalid. Please try again",
        hint="Shown when the user supplies an invalid key"
    )
    passwordRecoveryUserNotFound = i18n.translate(
        key="viur.modules.user.passwordrecovery.usernotfound",
        defaultText="There is no account with this name",
        hint="We cant find an account with that name (Should never happen)"
    )
    passwordRecoveryAccountLocked = i18n.translate(
        key="viur.modules.user.passwordrecovery.accountlocked",
        defaultText="This account is currently locked. You cannot change it's password.",
        hint="Attempted password recovery on a locked account"
    )

    @classmethod
    def getAuthMethodName(*args, **kwargs):
        return "X-VIUR-AUTH-User-Password"

    class LoginSkel(skeleton.RelSkel):
        name = EmailBone(descr="E-Mail", required=True, caseSensitive=False, indexed=True)
        password = PasswordBone(descr="Password", indexed=True, params={"justinput": True}, required=True)

    class LostPasswordStep1Skel(skeleton.RelSkel):
        name = EmailBone(descr="Username", required=True)

    class LostPasswordStep2Skel(skeleton.RelSkel):
        recovery_key = StringBone(
            descr="Recovery Key",
            visible=False,
        )
        password = PasswordBone(
            descr="New Password",
            required=True,
        )

    @exposed
    @force_ssl
    @skey(allow_empty=True)
    def login(self, *, name: str | None = None, password: str | None = None, **kwargs):
        if current.user.get():  # User is already logged in, nothing to do.
            return self._user_module.render.loginSucceeded()

        if not name or not password:
            return self._user_module.render.login(self.LoginSkel())

        self.loginRateLimit.assertQuotaIsAvailable()

        name = name.lower().strip()
        query = db.Query(self._user_module.viewSkel().kindName)
        user_entry = query.filter("name.idx >=", name).getEntry() or {}  # might find another user; always keep a dict

        password_data = user_entry.get("password") or {}
        # old password hashes used 1001 iterations
        iterations = password_data.get("iterations", 1001)
        passwd = encode_password(password, password_data.get("salt", "-invalid-"), iterations)["pwhash"]

        # Check if the username matches
        stored_user_name = (user_entry.get("name") or {}).get("idx") or ""
        is_okay = secrets.compare_digest(stored_user_name, name)

        # Check if the password matches
        stored_password_hash = password_data.get("pwhash", b"-invalid-")
        is_okay &= secrets.compare_digest(stored_password_hash, passwd)

        status = None

        # Verify that this account isn't blocked
        if (user_entry.get("status") or 0) < Status.ACTIVE.value:
            if is_okay:
                # The username and password is valid, in this case we can inform that user about his account status
                # (ie account locked or email verification pending)
                status = user_entry["status"]

            is_okay = False

        if not is_okay:
            self.loginRateLimit.decrementQuota()  # Only failed login attempts will count to the quota
            skel = self.LoginSkel()
            return self._user_module.render.login(skel, loginFailed=True, accountStatus=status)

        if iterations < PBKDF2_DEFAULT_ITERATIONS:
            logging.info(f"Update password hash for user {name}.")
            # re-hash the password with more iterations
            skel = self._user_module.editSkel()
            skel.setEntity(user_entry)
            skel["key"] = user_entry.key
            skel["password"] = password  # will be hashed on serialize
            skel.toDB(update_relations=False)

        return self.on_login(user_entry)

    def on_login(self, user_entry: db.Entity):
        """
        Hook that is called whenever the password authentication was successful.
        It allows to perform further steps in custom UserPassword authentications.
        """
        return self._user_module.continueAuthenticationFlow(self, user_entry.key)

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
                duration=15 * 60,
                key_length=conf["viur.security.password_recovery_key_length"],
                user_name=skel["name"].lower(),
                session_bound=False,
            )

            # Send the code in background
            self.sendUserPasswordRecoveryCode(
                skel["name"], recovery_key, current_request.request.headers["User-Agent"]
            )

            return self._user_module.render.view(None, tpl=self.passwordRecoveryInstructionsSentTemplate)

        # in step 2
        skel = self.LostPasswordStep2Skel()

        # check for any input; Render input-form when incomplete.
        skel["recovery_key"] = recovery_key
        if not skel.fromClient(kwargs) or not current_request.isPostRequest:
            return self._user_module.render.edit(
                skel=skel,
                tpl=self.passwordRecoveryStep2Template,
                recovery_key=recovery_key
            )

        # validate security key
        if not securitykey.validate(skey):
            raise errors.PreconditionFailed()

        if not (recovery_request := securitykey.validate(recovery_key, session_bound=False)):
            return self._user_module.render.view(
                skel=None,
                tpl=self.passwordRecoveryFailedTemplate,
                reason=self.passwordRecoveryKeyExpired)

        self.passwordRecoveryRateLimit.decrementQuota()

        # If we made it here, the key was correct, so we'd hopefully have a valid user for this
        user_skel = self._user_module.viewSkel().all().filter("name.idx =", recovery_request["user_name"]).getSkel()

        if not user_skel:
            # This *should* never happen - if we don't have a matching account we'll not send the key.
            return self._user_module.render.view(
                skel=None,
                tpl=self.passwordRecoveryFailedTemplate,
                reason=self.passwordRecoveryUserNotFound)

        if user_skel["status"] != Status.ACTIVE:  # The account is locked or not yet validated. Abort the process.
            return self._user_module.render.view(
                skel=None,
                tpl=self.passwordRecoveryFailedTemplate,
                reason=self.passwordRecoveryAccountLocked
            )

        # Update the password, save the user, reset his session and show the success-template
        user_skel["password"] = skel["password"]
        user_skel.toDB(update_relations=False)

        return self._user_module.render.view(None, tpl=self.passwordRecoverySuccessTemplate)

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

        if not isinstance(data, dict) or not (skel := db.RunInTransaction(transact, data.get("userKey"))):
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
            or parse_bool(kwargs.get("bounce"))  # review before adding
        ):
            # render the skeleton in the version it could as far as it could be read.
            return self._user_module.render.add(skel)
        self._user_module.onAdd(skel)
        skel.toDB()
        if self.registrationEmailVerificationRequired and skel["status"] == Status.WAITING_FOR_EMAIL_VERIFICATION:
            # The user will have to verify his email-address. Create a skey and send it to his address
            skey = securitykey.create(duration=60 * 60 * 24 * 7, session_bound=False,
                                      userKey=utils.normalizeKey(skel["key"]),
                                      name=skel["name"])
            skel.skey = BaseBone(descr="Skey")
            skel["skey"] = skey
            email.sendEMail(dests=[skel["name"]], tpl=self._user_module.verifyEmailAddressMail, skel=skel)
        self._user_module.onAdded(skel)  # Call onAdded on our parent user module
        return self._user_module.render.addSuccess(skel)


class GoogleAccount(UserAuthentication):
    registrationEnabled = False

    @classmethod
    def getAuthMethodName(*args, **kwargs):
        return "X-VIUR-AUTH-Google-Account"

    @exposed
    @force_ssl
    @skey(allow_empty=True)
    def login(self, token: str | None = None, *args, **kwargs):
        # FIXME: Check if already logged in
        if not conf.get("viur.user.google.clientID"):
            raise errors.PreconditionFailed("Please configure 'viur.user.google.clientID' in your conf!")
        if not token:
            request = current.request.get()
            request.response.headers["Content-Type"] = "text/html"
            if request.response.headers.get("cross-origin-opener-policy") == "same-origin":
                # We have to allow popups here
                request.response.headers["cross-origin-opener-policy"] = "same-origin-allow-popups"
            # Fixme: Render with Jinja2?
            with (conf["viur.instance.core_base_path"]
                  .joinpath("viur/core/template/vi_user_google_login.html")
                  .open() as tpl_file):
                tplStr = tpl_file.read()
            tplStr = tplStr.replace("{{ clientID }}", conf["viur.user.google.clientID"])
            extendCsp({"script-src": ["sha256-JpzaUIxV/gVOQhKoDLerccwqDDIVsdn1JclA6kRNkLw="],
                       "style-src": ["sha256-FQpGSicYMVC5jxKGS5sIEzrRjSJmkxKPaetUc7eamqc="]})
            return tplStr
        userInfo = id_token.verify_oauth2_token(token, requests.Request(), conf["viur.user.google.clientID"])
        if userInfo['iss'] not in {'accounts.google.com', 'https://accounts.google.com'}:
            raise ValueError('Wrong issuer.')
        # Token looks valid :)
        uid = userInfo['sub']
        email = userInfo['email']

        # fixme: use self._user_module.baseSkel() for this later
        addSkel = skeleton.skeletonByKind(self._user_module.addSkel().kindName)  # Ensure that we have the full skeleton

        update = False
        if not (userSkel := addSkel().all().filter("uid =", uid).getSkel()):
            # We'll try again - checking if there's already an user with that email
            if not (userSkel := addSkel().all().filter("name.idx =", email.lower()).getSkel()):
                # Still no luck - it's a completely new user
                if not self.registrationEnabled:
                    if (domain := userInfo.get("hd")) and domain in conf["viur.user.google.gsuiteDomains"]:
                        logging.debug(f"Google user is from allowed {domain} - adding account")
                    else:
                        logging.debug(f"Google user is from {domain} - denying registration")
                        raise errors.Forbidden("Registration for new users is disabled")

                userSkel = addSkel()  # We'll add a new user

            userSkel["uid"] = uid
            userSkel["name"] = email
            update = True

        # Take user information from Google, if wanted!
        if userSkel["sync"]:

            for target, source in {
                "name": email,
                "firstname": userInfo.get("given_name"),
                "lastname": userInfo.get("family_name"),
            }.items():

                if userSkel[target] != source:
                    userSkel[target] = source
                    update = True

        if update:
            # TODO: Get access from IAM or similar
            # if users.is_current_user_admin():
            #    if not userSkel["access"]:
            #        userSkel["access"] = []
            #    if not "root" in userSkel["access"]:
            #        userSkel["access"].append("root")
            #    userSkel["gaeadmin"] = True
            # else:
            #    userSkel["gaeadmin"] = False
            assert userSkel.toDB()

        return self._user_module.continueAuthenticationFlow(self, userSkel["key"])


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

    @abc.abstractmethod
    def can_handle(self, possible_user: db.Entity) -> bool:
        pass


class TimeBasedOTP(UserSecondFactorAuthentication):
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
        algorithm: typing.Literal["sha1", "sha256"] = "sha1"
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
    def get2FactorMethodName(*args, **kwargs):  # fixme: What is the purpose of this function? Why not just a member?
        return "X-VIUR-2FACTOR-TimeBasedOTP"

    def get_config(self, possible_user: db.Entity) -> OtpConfig | None:
        """
        Returns an instance of self.OtpConfig with a provided token configuration,
        or None when there is no appropriate configuration of this second factor handler available.
        """

        if possible_user.get("otp_secret"):
            return self.OtpConfig(secret=possible_user["otp_secret"], timedrift=possible_user.get("otp_timedrift") or 0)

        return None

    def can_handle(self, possible_user: db.Entity) -> bool:
        """
        Specified whether the second factor authentication can be handled by the given user or not.
        """
        return bool(self.get_config(possible_user))

    @exposed
    def start(self):
        """
        Configures OTP login for the current session.

        A special otp_user_conf has to be specified as a dict, which is stored into the session.
        """
        session = current.session.get()

        user_key = db.Key(self._user_module.kindName, session["possible_user_key"])
        if not (otp_user_conf := self.get_config(db.Get(user_key))):
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
                "name": translate(self.NAME),
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
                name=translate(self.NAME),
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
                name=translate(self.NAME),
                add_url=self.add_url,
                otp_uri=AuthenticatorOTP.generate_otp_app_secret_uri(otp_app_secret))
        else:
            if not AuthenticatorOTP.verify_otp(otp, otp_app_secret):
                return self._user_module.render.second_factor_add(
                    tpl=self.second_factor_add_template,
                    action_name=self.ACTION_NAME,
                    name=translate(self.NAME),
                    add_url=self.add_url,
                    otp_uri=AuthenticatorOTP.generate_otp_app_secret_uri(otp_app_secret))  # to add errors

            # Now we can set the otp_app_secret to the current User and render der Success-template
            AuthenticatorOTP.set_otp_app_secret(otp_app_secret)
            return self._user_module.render.second_factor_add_success(
                action_name=self.ACTION_NAME,
                name=translate(self.NAME),
            )

    def can_handle(self, possible_user: db.Entity) -> bool:
        """
        We can only handle the second factor if we have stored an otp_app_secret before.
        """
        return bool(possible_user.get("otp_app_secret", ""))

    @classmethod
    def get2FactorMethodName(*args, **kwargs) -> str:
        return "X-VIUR-2FACTOR-AuthenticatorOTP"

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
        if not (issuer := conf["viur.otp.issuer"]):
            logging.warning(
                f"""conf["viur.otp.issuer"] is None we replace the issuer by conf["viur.instance.project_id"]""")
            issuer = conf["viur.instance.project_id"]

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
                "name": translate(self.NAME),
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
            name=translate(self.NAME),
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

    authenticationProviders: list[UserAuthentication] = [UserPassword, GoogleAccount]
    secondFactorProviders: list[UserSecondFactorAuthentication] = [TimeBasedOTP, AuthenticatorOTP]
    validAuthenticationMethods = [
        (UserPassword, AuthenticatorOTP),
        (UserPassword, TimeBasedOTP),
        (UserPassword, None),
        (GoogleAccount, None),
    ]

    secondFactorTimeWindow = datetime.timedelta(minutes=10)

    adminInfo = {
        "icon": "users",
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
                "icon": "trash",
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
                "icon": "interface",
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
            assert issubclass(provider, UserAuthentication)
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
        skel = super(User, self).addSkel().clone()
        user = current.user.get()
        if not (user and user["access"] and ("%s-add" % self.moduleName in user["access"] or "root" in user["access"])):
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
        skel = super(User, self).editSkel().clone()

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
        return getattr(self, "f2_%s" % cls.__name__.lower())

    def getCurrentUser(self):
        # May be a deferred task
        if not (session := current.session.get()):
            return None

        if user := session.get("user"):
            skel = self.baseSkel()
            skel.setEntity(user)
            return skel

        return None

    def continueAuthenticationFlow(self, caller, userKey):
        session = current.session.get()
        session["possible_user_key"] = userKey.id_or_name
        session["_secondFactorStart"] = utils.utcNow()
        session.markChanged()

        second_factor_providers = []

        if not (possible_user := db.Get(userKey)):
            raise errors.NotFound()
        for auth_provider, second_factor in self.validAuthenticationMethods:
            if isinstance(caller, auth_provider):
                if second_factor is not None:
                    second_factor_provider_instance = self.secondFactorProviderByClass(second_factor)
                    if second_factor_provider_instance.can_handle(possible_user):
                        second_factor_providers.append(second_factor_provider_instance)
                else:
                    second_factor_providers.append(None)
        if len(second_factor_providers) > 1 and None in second_factor_providers:
            # We have a second factor. So we can get rid of the None
            second_factor_providers.pop(second_factor_providers.index(None))

        if len(second_factor_providers) == 0:
            raise errors.NotAcceptable("There are no authentication methods to try")
        elif len(second_factor_providers) == 1:
            if second_factor_providers[0] is None:
                # We allow sign-in without a second factor
                return self.authenticateUser(userKey)
            # We have only one second factor we don't need the choice template
            return second_factor_providers[0].start(userKey)
        # In case there is more than one second factor, let the user select a method.
        return self.render.second_factor_choice(second_factors=second_factor_providers)

    def secondFactorSucceeded(self, secondFactor, userKey):
        session = current.session.get()
        if session["possible_user_key"] != userKey.id_or_name:
            raise errors.Forbidden()
        # Assert that the second factor verification finished in time
        if utils.utcNow() - session["_secondFactorStart"] > self.secondFactorTimeWindow:
            raise errors.RequestTimeout()
        return self.authenticateUser(userKey)

    def authenticateUser(self, key: db.Key, **kwargs):
        """
            Performs Log-In for the current session and the given user key.

            This resets the current session: All fields not explicitly marked as persistent
            by conf["viur.session.persistentFieldsOnLogin"] are gone afterwards.

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
        take_over = {k: v for k, v in session.items() if k in conf["viur.session.persistentFieldsOnLogin"]}
        session.reset()
        # and copy them over to the new session
        session |= take_over

        # Update session, user and request
        session["user"] = skel.dbEntity

        current.request.get().response.headers[securitykey.SECURITYKEY_STATIC] = session.static_security_key
        current.user.set(self.getCurrentUser())

        self.onLogin(skel)

        return self.render.loginSucceeded(**kwargs)

    @exposed
    @skey
    def logout(self, *args, **kwargs):
        """
            Implements the logout action. It also terminates the current session (all keys not listed
            in viur.session.persistentFieldsOnLogout will be lost).
        """
        if not (user := current.user.get()):
            raise errors.Unauthorized()

        self.onLogout(user)

        session = current.session.get()
        take_over = {k: v for k, v in session.items() if k in conf["viur.session.persistentFieldsOnLogout"]}
        session.reset()
        session |= take_over
        current.user.set(None)  # set user to none in context var
        return self.render.logoutSuccess()

    @exposed
    def login(self, *args, **kwargs):
        authMethods = [(x.getAuthMethodName(), y.get2FactorMethodName() if y else None)
                       for x, y in self.validAuthenticationMethods]
        return self.render.loginChoices(authMethods)

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
        res = []

        for auth, secondFactor in self.validAuthenticationMethods:
            res.append([auth.getAuthMethodName(), secondFactor.get2FactorMethodName() if secondFactor else None])

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
    userMod = getattr(conf["viur.mainApp"], "user", None)
    if (userMod  # We have a user module
        and isinstance(userMod, User)
        and "addSkel" in dir(userMod)
        and "validAuthenticationMethods" in dir(userMod)  # Its our user module :)
        and any([issubclass(x[0], UserPassword) for x in
                 userMod.validAuthenticationMethods])):  # It uses UserPassword login
        if not db.Query(userMod.addSkel().kindName).getEntry():  # There's currently no user in the database
            addSkel = skeleton.skeletonByKind(userMod.addSkel().kindName)()  # Ensure we have the full skeleton
            uname = f"""admin@{conf["viur.instance.project_id"]}.appspot.com"""
            pw = utils.generateRandomString(13)
            addSkel["name"] = uname
            addSkel["status"] = Status.ACTIVE  # Ensure it's enabled right away
            addSkel["access"] = ["root"]
            addSkel["password"] = pw

            try:
                addSkel.toDB()
            except Exception as e:
                logging.error("Something went wrong when trying to add admin user %s with Password %s", uname, pw)
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
