import datetime
import enum
import functools
import hashlib
import hmac
import json
import logging
import secrets
import warnings
from typing import Optional

import time
from google.auth.transport import requests
from google.oauth2 import id_token

from viur.core import (
    conf, current, db, email, errors, exposed, forceSSL, i18n,
    securitykey, session, skeleton, tasks, utils
)
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
    access = SelectBone(
        descr="Access rights",
        values=lambda: {
            right: i18n.translate("server.modules.user.accessright.%s" % right, defaultText=right)
            for right in sorted(conf["viur.accessRights"])
        },
        multiple=True,
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
    otpid = StringBone(
        descr="OTP serial",
        required=False,
        searchable=True,
    )

    otpkey = CredentialBone(
        descr="OTP hex key",
        required=False,
    )

    otptimedrift = NumericBone(
        descr="OTP time drift",
        readOnly=True,
        defaultValue=0,
    )

    admin_config = JsonBone(  # This bone stores settings from the vi
        descr="Config for the User",
        visible=False
    )


class UserPassword:
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
    passwordRecoveryInstuctionsSendTemplate = "user_passwordrecover_mail_sent"
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

    def __init__(self, userModule, modulePath):
        super().__init__()
        self.userModule = userModule
        self.modulePath = modulePath

    @classmethod
    def getAuthMethodName(*args, **kwargs):
        return "X-VIUR-AUTH-User-Password"

    class LoginSkel(skeleton.RelSkel):
        name = EmailBone(descr="E-Mail", required=True, caseSensitive=False, indexed=True)
        password = PasswordBone(descr="Password", indexed=True, params={"justinput": True}, required=True)

    class LostPasswordStep1Skel(skeleton.RelSkel):
        name = EmailBone(descr="Username", required=True)
        captcha = CaptchaBone(descr="Captcha", required=True)

    class LostPasswordStep2Skel(skeleton.RelSkel):
        recoveryKey = StringBone(descr="Verification Code", required=True)
        password = PasswordBone(descr="New Password", required=True)

    @exposed
    @forceSSL
    def login(self, name=None, password=None, skey="", *args, **kwargs):
        if current.user.get():  # User is already logged in, nothing to do.
            return self.userModule.render.loginSucceeded()

        if not name or not password or not securitykey.validate(skey, useSessionKey=True):
            return self.userModule.render.login(self.LoginSkel())

        self.loginRateLimit.assertQuotaIsAvailable()

        name = name.lower().strip()
        query = db.Query(self.userModule.viewSkel().kindName)
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

        status: Optional[int] = None
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
            return self.userModule.render.login(skel, loginFailed=True, accountStatus=status)

        if iterations < PBKDF2_DEFAULT_ITERATIONS:
            logging.info(f"Update password hash for user {name}.")
            # re-hash the password with more iterations
            skel = self.userModule.editSkel()
            skel.setEntity(user_entry)
            skel["key"] = user_entry.key
            skel["password"] = password  # will be hashed on serialize
            skel.toDB(update_relations=False)

        return self.userModule.continueAuthenticationFlow(self, user_entry.key)

    @exposed
    def pwrecover(self, *args, **kwargs):
        """
            This implements the password recovery process which let them set a new password for their account
            after validating a code send to them by email. The process is as following:

            - The user enters his email adress
            - We'll generate a random code, store it in his session and call sendUserPasswordRecoveryCode
            - sendUserPasswordRecoveryCode will run in the background, check if we have a user with that name
              and send the code. It runs as a deferredTask so we don't leak the information if a user account exists.
            - If the user received his code, he can paste the code and set a new password for his account.

            To prevent automated attacks, the fist step is guarded by a captcha and we limited calls to this function
            to 10 actions per 15 minutes. (One complete recovery process consists of two calls).
        """
        self.passwordRecoveryRateLimit.assertQuotaIsAvailable()
        session = current.session.get()
        request = current.request.get()
        recoverStep = session.get("user.auth_userpassword.pwrecover")
        if not recoverStep:
            # This is the first step, where we ask for the username of the account we'll going to reset the password on
            skel = self.LostPasswordStep1Skel()
            if not request.isPostRequest or not skel.fromClient(kwargs):
                return self.userModule.render.edit(skel, tpl=self.passwordRecoveryStep1Template)
            if not securitykey.validate(kwargs.get("skey"), useSessionKey=True):
                raise errors.PreconditionFailed()
            self.passwordRecoveryRateLimit.decrementQuota()
            recoveryKey = utils.generateRandomString(13)  # This is the key the user will have to Copy&Paste
            self.sendUserPasswordRecoveryCode(skel["name"].lower(), recoveryKey)  # Send the code in the background
            session["user.auth_userpassword.pwrecover"] = {
                "name": skel["name"].lower(),
                "recoveryKey": recoveryKey,
                "creationdate": utils.utcNow(),
                "errorCount": 0
            }
            del recoveryKey
            return self.pwrecover()  # Fall through to the second step as that key in the session is now set
        else:
            if request.isPostRequest and kwargs.get("abort") == "1" \
                and securitykey.validate(kwargs.get("skey"), useSessionKey=True):
                # Allow a user to abort the process if a wrong email has been used
                session["user.auth_userpassword.pwrecover"] = None
                return self.pwrecover()
            # We're in the second step - the code has been send and is waiting for confirmation from the user
            if utils.utcNow() - session["user.auth_userpassword.pwrecover"]["creationdate"] \
                    > datetime.timedelta(minutes=15):
                # This recovery-process is expired; reset the session and start over
                session["user.auth_userpassword.pwrecover"] = None
                return self.userModule.render.view(
                    skel=None,
                    tpl=self.passwordRecoveryFailedTemplate,
                    reason=self.passwordRecoveryKeyExpired)
            skel = self.LostPasswordStep2Skel()
            if not skel.fromClient(kwargs) or not request.isPostRequest:
                return self.userModule.render.edit(skel, tpl=self.passwordRecoveryStep2Template)
            if not securitykey.validate(kwargs.get("skey"), useSessionKey=True):
                raise errors.PreconditionFailed()
            self.passwordRecoveryRateLimit.decrementQuota()
            if not hmac.compare_digest(session["user.auth_userpassword.pwrecover"]["recoveryKey"], skel["recoveryKey"]):
                # The key was invalid, increase error-count or abort this recovery process altogether
                session["user.auth_userpassword.pwrecover"]["errorCount"] += 1
                if session["user.auth_userpassword.pwrecover"]["errorCount"] > 3:
                    session["user.auth_userpassword.pwrecover"] = None
                    return self.userModule.render.view(
                        skel=None,
                        tpl=self.passwordRecoveryFailedTemplate,
                        reason=self.passwordRecoveryKeyInvalid)

                return self.userModule.render.edit(skel, tpl=self.passwordRecoveryStep2Template)  # Let's try again

            # If we made it here, the key was correct, so we'd hopefully have a valid user for this
            user_skel = self.userModule.viewSkel().all().filter(
                "name.idx =", session["user.auth_userpassword.pwrecover"]["name"]).getSkel()

            if not user_skel:
                # This *should* never happen - if we don't have a matching account we'll not send the key.
                session["user.auth_userpassword.pwrecover"] = None
                return self.userModule.render.view(
                    skel=None,
                    tpl=self.passwordRecoveryFailedTemplate,
                    reason=self.passwordRecoveryUserNotFound)

            if user_skel["status"] != Status.ACTIVE:
                # The account is locked or not yet validated. Abort the process.
                session["user.auth_userpassword.pwrecover"] = None
                return self.userModule.render.view(
                    skel=None,
                    tpl=self.passwordRecoveryFailedTemplate,
                    reason=self.passwordRecoveryAccountLocked)

            # Update the password, save the user, reset his session and show the success-template
            user_skel["password"] = skel["password"]
            user_skel.toDB()
            session["user.auth_userpassword.pwrecover"] = None

            return self.userModule.render.view(None, tpl=self.passwordRecoverySuccessTemplate)

    @tasks.CallDeferred
    def sendUserPasswordRecoveryCode(self, userName: str, recoveryKey: str) -> None:
        """
            Sends the given recovery code to the user given in userName. This function runs deferred
            so there's no timing sidechannel that leaks if this user exists. Per default, we'll send the
            code by email (assuming we have working email delivery), but this can be overridden to send it
            by SMS or other means. We'll also update the changedate for this user, so no more than one code
            can be send to any given user in four hours.
        """

        def updateChangeDateTxn(key):
            obj = db.Get(key)
            obj["changedate"] = utils.utcNow()
            db.Put(obj)

        user = db.Query("user").filter("name.idx =", userName).getEntry()
        if user:
            if user.get("changedate") and user["changedate"] > utils.utcNow() - datetime.timedelta(hours=4):
                # There is a changedate and the user has been modified in the last 4 hours - abort
                return
            # Update the changedate so no more than one email is send per 4 hours
            db.RunInTransaction(updateChangeDateTxn, user.key)
            email.sendEMail(tpl=self.passwordRecoveryMail, skel={"recoveryKey": recoveryKey}, dests=[userName])

    @exposed
    def verify(self, skey, *args, **kwargs):
        data = securitykey.validate(skey, useSessionKey=False)
        skel = self.userModule.editSkel()
        if not data or not isinstance(data, dict) or "userKey" not in data or not skel.fromDB(
            data["userKey"].id_or_name):
            return self.userModule.render.view(None, tpl=self.verifyFailedTemplate)
        if self.registrationAdminVerificationRequired:
            skel["status"] = Status.WAITING_FOR_ADMIN_VERIFICATION
        else:
            skel["status"] = Status.ACTIVE
        skel.toDB()
        return self.userModule.render.view(skel, tpl=self.verifySuccessTemplate)

    def canAdd(self) -> bool:
        return self.registrationEnabled

    def addSkel(self):
        """
            Prepare the add-Skel for rendering.
            Currently only calls self.userModule.addSkel() and sets skel["status"] depending on
            self.registrationEmailVerificationRequired and self.registrationAdminVerificationRequired
            :return: viur.core.skeleton.Skeleton
        """
        skel = self.userModule.addSkel()

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

    @forceSSL
    @exposed
    def add(self, *args, **kwargs):
        """
            Allows guests to register a new account if self.registrationEnabled is set to true

            .. seealso:: :func:`addSkel`, :func:`onAdded`, :func:`canAdd`

            :returns: The rendered, added object of the entry, eventually with error hints.

            :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
            :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        skey = kwargs.get("skey", "")
        if not self.canAdd():
            raise errors.Unauthorized()
        skel = self.addSkel()
        if (len(kwargs) == 0  # no data supplied
            or not current.request.get().isPostRequest  # bail out if not using POST-method
            or not skel.fromClient(kwargs)  # failure on reading into the bones
            or ("bounce" in kwargs and kwargs["bounce"] == "1")):  # review before adding
            # render the skeleton in the version it could as far as it could be read.
            return self.userModule.render.add(skel)
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()
        skel.toDB()
        if self.registrationEmailVerificationRequired and skel["status"] == Status.WAITING_FOR_EMAIL_VERIFICATION:
            # The user will have to verify his email-address. Create a skey and send it to his address
            skey = securitykey.create(duration=60 * 60 * 24 * 7, userKey=utils.normalizeKey(skel["key"]),
                                      name=skel["name"])
            skel.skey = BaseBone(descr="Skey")
            skel["skey"] = skey
            email.sendEMail(dests=[skel["name"]], tpl=self.userModule.verifyEmailAddressMail, skel=skel)
        self.userModule.onAdded(skel)  # Call onAdded on our parent user module
        return self.userModule.render.addSuccess(skel)


class GoogleAccount:
    registrationEnabled = False

    def __init__(self, userModule, modulePath):
        super().__init__()
        self.userModule = userModule
        self.modulePath = modulePath

    @classmethod
    def getAuthMethodName(*args, **kwargs):
        return "X-VIUR-AUTH-Google-Account"

    @exposed
    @forceSSL
    def login(self, skey="", token="", *args, **kwargs):
        # FIXME: Check if already logged in
        if not conf.get("viur.user.google.clientID"):
            raise errors.PreconditionFailed("Please configure 'viur.user.google.clientID' in your conf!")
        if not skey or not token:
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
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()
        userInfo = id_token.verify_oauth2_token(token, requests.Request(), conf["viur.user.google.clientID"])
        if userInfo['iss'] not in {'accounts.google.com', 'https://accounts.google.com'}:
            raise ValueError('Wrong issuer.')
        # Token looks valid :)
        uid = userInfo['sub']
        email = userInfo['email']

        # fixme: use self.userModule.baseSkel() for this later
        addSkel = skeleton.skeletonByKind(self.userModule.addSkel().kindName)  # Ensure that we have the full skeleton

        update = False
        if not (userSkel := addSkel().all().filter("uid =", uid).getSkel()):
            # We'll try again - checking if there's already an user with that email
            if not (userSkel := addSkel().all().filter("name.idx =", email.lower()).getSkel()):
                # Still no luck - it's a completely new user
                if not self.registrationEnabled:
                    if userInfo.get("hd") and userInfo["hd"] in conf["viur.user.google.gsuiteDomains"]:
                        print("User is from domain - adding account")
                    else:
                        logging.warning("Denying registration of %s", email)
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

        return self.userModule.continueAuthenticationFlow(self, userSkel["key"])


class TimeBasedOTP:
    windowSize = 5
    otpTemplate = "user_login_timebasedotp"

    def __init__(self, userModule, modulePath):
        super().__init__()
        self.userModule = userModule
        self.modulePath = modulePath

    @classmethod
    def get2FactorMethodName(*args, **kwargs):
        return "X-VIUR-2FACTOR-TimeBasedOTP"

    def canHandle(self, userKey) -> bool:
        user = db.Get(userKey)
        return all(
            [(x in user and (x == "otptimedrift" or bool(user[x]))) for x in ["otpid", "otpkey", "otptimedrift"]])

    def startProcessing(self, userKey):
        user = db.Get(userKey)
        if all([(x in user and user[x]) for x in ["otpid", "otpkey"]]):
            logging.info("OTP wanted for user")
            session = current.session.get()
            session["_otp_user"] = {
                "uid": str(userKey),
                "otpid": user["otpid"],
                "otpkey": user["otpkey"],
                "otptimedrift": user["otptimedrift"],
                "timestamp": time.time(),
                "failures": 0
            }
            session.markChanged()
            return self.userModule.render.loginSucceeded(msg="X-VIUR-2FACTOR-TimeBasedOTP")

        return None

    class OtpSkel(skeleton.RelSkel):
        otptoken = StringBone(descr="Token", required=True, caseSensitive=False, indexed=True)

    def generateOtps(self, secret, timeDrift):
        """
            Generates all valid tokens for the given secret
        """

        def asBytes(valIn):
            """
                Returns the integer in binary representation
            """
            hexStr = hex(valIn)[2:]
            # Maybe uneven length
            if len(hexStr) % 2 == 1:
                hexStr = "0" + hexStr
            return bytes.fromhex("00" * int(8 - (len(hexStr) / 2)) + hexStr)

        idx = int(time.time() / 60.0)  # Current time index
        idx += int(timeDrift)
        res = []
        for slot in range(idx - self.windowSize, idx + self.windowSize):
            currHash = hmac.new(bytes.fromhex(secret), asBytes(slot), hashlib.sha1).digest()
            # Magic code from https://tools.ietf.org/html/rfc4226 :)
            offset = currHash[19] & 0xf
            code = ((currHash[offset] & 0x7f) << 24 |
                    (currHash[offset + 1] & 0xff) << 16 |
                    (currHash[offset + 2] & 0xff) << 8 |
                    (currHash[offset + 3] & 0xff))
            res.append(int(str(code)[-6:]))  # We use only the last 6 digits
        return res

    @exposed
    @forceSSL
    def otp(self, otptoken=None, skey=None, *args, **kwargs):
        session = current.session.get()
        token = session.get("_otp_user")
        if not token:
            raise errors.Forbidden()
        if otptoken is None:
            self.userModule.render.edit(self.OtpSkel())
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()
        if token["failures"] > 3:
            raise errors.Forbidden("Maximum amount of authentication retries exceeded")
        if len(token["otpkey"]) % 2 == 1:
            raise errors.PreconditionFailed("The otp secret stored for this user is invalid (uneven length)")
        validTokens = self.generateOtps(token["otpkey"], token["otptimedrift"])
        try:
            otptoken = int(otptoken)
        except:
            # We got a non-numeric token - this can't be correct
            self.userModule.render.edit(self.OtpSkel(), tpl=self.otpTemplate)

        if otptoken in validTokens:
            userKey = session["_otp_user"]["uid"]

            del session["_otp_user"]
            session.markChanged()

            idx = validTokens.index(int(otptoken))

            if abs(idx - self.windowSize) > 2:
                # The time-drift accumulates to more than 2 minutes, update our
                # clock-drift value accordingly
                self.updateTimeDrift(userKey, idx - self.windowSize)

            return self.userModule.secondFactorSucceeded(self, userKey)
        else:
            token["failures"] += 1
            session["_otp_user"] = token
            session.markChanged()
            return self.userModule.render.edit(self.OtpSkel(), loginFailed=True, tpl=self.otpTemplate)

    def updateTimeDrift(self, userKey, idx):
        """
            Updates the clock-drift value.
            The value is only changed in 1/10 steps, so that a late submit by an user doesn't skew
            it out of bounds. Maximum change per call is 0.3 minutes.
            :param userKey: For which user should the update occour
            :param idx: How many steps before/behind was that token
            :return:
        """

        def updateTransaction(userKey, idx):
            user = db.Get(userKey)
            if not "otptimedrift" in user or not isinstance(user["otptimedrift"], float):
                user["otptimedrift"] = 0.0
            user["otptimedrift"] += min(max(0.1 * idx, -0.3), 0.3)
            db.Put(user)

        db.RunInTransaction(updateTransaction, userKey, idx)


class User(List):
    kindName = "user"
    addTemplate = "user_add"
    addSuccessTemplate = "user_add_success"
    lostPasswordTemplate = "user_lostpassword"
    verifyEmailAddressMail = "user_verify_address"
    passwordRecoveryMail = "user_password_recovery"

    authenticationProviders = [UserPassword, GoogleAccount]
    secondFactorProviders = [TimeBasedOTP]

    validAuthenticationMethods = [(UserPassword, TimeBasedOTP), (UserPassword, None), (GoogleAccount, None)]

    secondFactorTimeWindow = datetime.timedelta(minutes=10)

    adminInfo = {
        "icon": "icon-users"
    }

    def __init__(self, moduleName, modulePath, *args, **kwargs):
        super().__init__(moduleName, modulePath, *args, **kwargs)

        # Initialize the login-providers
        self.initializedAuthenticationProviders = {}
        self.initializedSecondFactorProviders = {}
        self._viurMapSubmodules = []

        for p in self.authenticationProviders:
            pInstance = p(self, modulePath + "/auth_%s" % p.__name__.lower())
            self.initializedAuthenticationProviders[pInstance.__class__.__name__.lower()] = pInstance

            # Also put it as an object into self, so that any exposed function is reachable
            setattr(self, "auth_%s" % pInstance.__class__.__name__.lower(), pInstance)
            self._viurMapSubmodules.append("auth_%s" % pInstance.__class__.__name__.lower())

        for p in self.secondFactorProviders:
            pInstance = p(self, modulePath + "/f2_%s" % p.__name__.lower())
            self.initializedAuthenticationProviders[pInstance.__class__.__name__.lower()] = pInstance

            # Also put it as an object into self, so that any exposed function is reachable
            setattr(self, "f2_%s" % pInstance.__class__.__name__.lower(), pInstance)
            self._viurMapSubmodules.append("f2_%s" % pInstance.__class__.__name__.lower())

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

    def secondFactorProviderByClass(self, cls):
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
        session["_mayBeUserKey"] = userKey.id_or_name
        session["_secondFactorStart"] = utils.utcNow()
        session.markChanged()

        for authProvider, secondFactor in self.validAuthenticationMethods:
            if isinstance(caller, authProvider):
                if secondFactor is None:
                    # We allow sign-in without a second factor
                    return self.authenticateUser(userKey)
                # This Auth-Request was issued from this authenticationProvider
                secondFactorProvider = self.secondFactorProviderByClass(secondFactor)
                if secondFactorProvider.canHandle(userKey):
                    # We choose the first second factor provider which claims it can verify that user
                    return secondFactorProvider.startProcessing(userKey)
        # Whoops.. This user logged in successfully - but we have no second factor provider willing to confirm it
        raise errors.NotAcceptable("There are no more authentication methods to try")  # Sorry...

    def secondFactorSucceeded(self, secondFactor, userKey):
        session = current.session.get()
        logging.debug("Got SecondFactorSucceeded call from %s." % secondFactor)
        if session["_mayBeUserKey"] != userKey.id_or_name:
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

        current.request.get().response.headers["Sec-X-ViUR-StaticSKey"] = session.staticSecurityKey
        current.user.set(self.getCurrentUser())

        self.onLogin(skel)

        return self.render.loginSucceeded(**kwargs)

    @exposed
    def logout(self, skey="", *args, **kwargs):
        """
            Implements the logout action. It also terminates the current session (all keys not listed
            in viur.session.persistentFieldsOnLogout will be lost).
        """
        if not (user := current.user.get()):
            raise errors.Unauthorized()
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()

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
    def edit(self, *args, **kwargs):
        user = current.user.get()

        # fixme: This assumes that the user can edit itself when no parameters are provided...
        if len(args) == 0 and "key" not in kwargs and user:
            # it is not a security issue as super().edit() checks the access rights.
            kwargs["key"] = user["key"]

        return super().edit(*args, **kwargs)

    @exposed
    def view(self, key, *args, **kwargs):
        """
            Allow a special key "self" to reference always the current user
        """
        if key == "self":
            if not (user := current.user.get()):
                raise errors.Unauthorized()

            return super().view(str(user["key"].id_or_name), *args, **kwargs)

        return super().view(key, *args, **kwargs)

    def canView(self, skel) -> bool:
        if user := current.user.get():
            if skel["key"] == user["key"]:
                return True

            if "root" in user["access"] or "user-view" in user["access"]:
                return True

        return False

    @exposed
    def getAuthMethods(self, *args, **kwargs):
        """Inform tools like Viur-Admin which authentication to use"""
        res = []

        for auth, secondFactor in self.validAuthenticationMethods:
            res.append([auth.getAuthMethodName(), secondFactor.get2FactorMethodName() if secondFactor else None])

        return json.dumps(res)

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
            logging.warning("ViUR created a new admin-user for you! Username: %s, Password: %s", uname, pw)
            email.sendEMailToAdmins("Your new ViUR password",
                                    "ViUR created a new admin-user for you! Username: %s, Password: %s" % (uname, pw))


# DEPRECATED ATTRIBUTES HANDLING

def __getattr__(attr):
    match attr:
        case "userSkel":
            msg = f"Use of `userSkel` is deprecated; Please use `UserSkel` instead!"
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            logging.warning(msg)
            return UserSkel

    return super(__import__(__name__).__class__).__getattr__(attr)
