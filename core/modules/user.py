from viur.core.prototypes.list import List
from viur.core.skeleton import Skeleton, RelSkel, skeletonByKind
from viur.core.bones import *
from viur.core import utils, email
from viur.core.bones.base import ReadFromClientErrorSeverity, UniqueValue, UniqueLockMethod
from viur.core.bones.password import pbkdf2
from viur.core import errors, conf, securitykey
from viur.core.tasks import StartupTask, CallDeferred
from viur.core.securityheaders import extendCsp
from viur.core.ratelimit import RateLimit
from time import time
from viur.core import exposed, forceSSL, db
from hashlib import sha512
# from google.appengine.api import users, app_identity
import logging, os
import datetime
import hmac, hashlib
import json
from google.oauth2 import id_token
from google.auth.transport import requests
from viur.core.i18n import translate
from viur.core.utils import currentRequest, currentSession, utcNow
from viur.core.session import killSessionByUser
from typing import Optional


class userSkel(Skeleton):
    kindName = "user"

    # Properties required by google and custom auth
    name = EmailBone(
        descr=u"E-Mail",
        required=True,
        readOnly=True,
        caseSensitive=False,
        searchable=True,
        indexed=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, True, "Username already taken")
    )

    # Properties required by custom auth
    password = PasswordBone(
        descr=u"Password",
        required=False,
        readOnly=True,
        visible=False
    )

    # Properties required by google auth
    uid = StringBone(
        descr=u"Google's UserID",
        indexed=True,
        required=False,
        readOnly=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, False, "UID already in use")
    )
    gaeadmin = BooleanBone(
        descr=u"Is GAE Admin",
        defaultValue=False,
        readOnly=True
    )

    # Generic properties
    access = SelectBone(
        descr=u"Access rights",
        values=lambda: {
            right: translate("server.modules.user.accessright.%s" % right, defaultText=right)
                for right in sorted(conf["viur.accessRights"])
        },
        indexed=True,
        multiple=True
    )
    status = SelectBone(
        descr=u"Account status",
        values={
            1: u"Waiting for email verification",
            2: u"Waiting for verification through admin",
            5: u"Account disabled",
            10: u"Active"
        },
        defaultValue=10,
        required=True,
        indexed=True
    )
    lastlogin = DateBone(
        descr=u"Last Login",
        readOnly=True,
        indexed=True
    )

    # One-Time Password Verification
    otpid = StringBone(
        descr=u"OTP serial",
        required=False,
        indexed=True,
        searchable=True
    )
    otpkey = CredentialBone(
        descr=u"OTP hex key",
        required=False,
        indexed=True
    )
    otptimedrift = NumericBone(
        descr=u"OTP time drift",
        readOnly=True,
        defaultValue=0
    )


class UserPassword(object):
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
    passwordRecoveryKeyExpired = translate(
        key="viur.modules.user.passwordrecovery.keyexpired",
        defaultText="The key is expired. Please try again",
        hint="Shown when the user needs more than 10 minutes to paste the key"
    )
    passwordRecoveryKeyInvalid = translate(
        key="viur.modules.user.passwordrecovery.keyinvalid",
        defaultText="The key is invalid. Please try again",
        hint="Shown when the user supplies an invalid key"
    )
    passwordRecoveryUserNotFound = translate(
        key="viur.modules.user.passwordrecovery.usernotfound",
        defaultText="There is no account with this name",
        hint="We cant find an account with that name (Should never happen)"
    )
    passwordRecoveryAccountLocked = translate(
        key="viur.modules.user.passwordrecovery.accountlocked",
        defaultText="This account is currently locked. You cannot change it's password.",
        hint="Attempted password recovery on a locked account"
    )

    def __init__(self, userModule, modulePath):
        super(UserPassword, self).__init__()
        self.userModule = userModule
        self.modulePath = modulePath

    @classmethod
    def getAuthMethodName(*args, **kwargs):
        return u"X-VIUR-AUTH-User-Password"

    class loginSkel(RelSkel):
        name = EmailBone(descr="E-Mail", required=True, caseSensitive=False, indexed=True)
        password = PasswordBone(descr="Password", indexed=True, params={"justinput": True}, required=True)

    class lostPasswordStep1Skel(RelSkel):
        name = EmailBone(descr="Username", required=True)
        captcha = CaptchaBone(descr=u"Captcha", required=True)

    class lostPasswordStep2Skel(RelSkel):
        recoveryKey = StringBone(descr="Verification Code", required=True)
        password = PasswordBone(descr="New Password", required=True)

    @exposed
    @forceSSL
    def login(self, name=None, password=None, skey="", *args, **kwargs):
        if self.userModule.getCurrentUser():  # Were already logged in
            return self.userModule.render.loginSucceeded()

        if not name or not password or not securitykey.validate(skey, useSessionKey=True):
            return self.userModule.render.login(self.loginSkel())

        self.loginRateLimit.assertQuotaIsAvailable()

        name = name.lower().strip()
        query = db.Query(self.userModule.viewSkel().kindName)
        res = query.filter("name.idx >=", name).getEntry()

        if res is None:
            res = {"password": {"pwhash": "-invalid-", "salt": "-invalid"}, "status": 0, "name": {}}

        passwd = pbkdf2(password[:conf["viur.maxPasswordLength"]], (res.get("password", None) or {}).get("salt", ""))
        isOkay = True

        # We do this exactly that way to avoid timing attacks

        # Check if the username matches
        storedUserName = (res.get("name") or {}).get("idx", "")
        if len(storedUserName) != len(name):
            isOkay = False
        else:
            for x, y in zip(storedUserName, name):
                if x != y:
                    isOkay = False

        # Check if the password matches
        storedPasswordHash = (res.get("password", None) or {}).get("pwhash", "-invalid-")
        if len(storedPasswordHash) != len(passwd):
            isOkay = False
        else:
            for x, y in zip(storedPasswordHash, passwd):
                if x != y:
                    isOkay = False

        accountStatus: Optional[int] = None
        # Verify that this account isn't blocked
        if res["status"] < 10:
            if isOkay:
                # The username and password is valid, in this case we can inform that user about his account status
                # (ie account locked or email verification pending)
                accountStatus = res["status"]
            isOkay = False

        if not isOkay:
            self.loginRateLimit.decrementQuota()  # Only failed login attempts will count to the quota
            skel = self.loginSkel()
            return self.userModule.render.login(skel, loginFailed=True, accountStatus=accountStatus)
        else:
            return self.userModule.continueAuthenticationFlow(self, res.key)

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
        session = currentSession.get()
        request = currentRequest.get()
        recoverStep = session.get("user.auth_userpassword.pwrecover")
        if not recoverStep:
            # This is the first step, where we ask for the username of the account we'll going to reset the password on
            skel = self.lostPasswordStep1Skel()
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
                "creationdate": utcNow(),
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
            if utcNow() - session["user.auth_userpassword.pwrecover"]["creationdate"] > datetime.timedelta(minutes=15):
                # This recovery-process is expired; reset the session and start over
                session["user.auth_userpassword.pwrecover"] = None
                return self.userModule.render.view(
                    skel=None,
                    tpl=self.passwordRecoveryFailedTemplate,
                    reason=self.passwordRecoveryKeyExpired)
            skel = self.lostPasswordStep2Skel()
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
            uSkel = userSkel().all().filter("name.idx =", session["user.auth_userpassword.pwrecover"]["name"]).getSkel()
            if not uSkel:  # This *should* never happen - if we don't have a matching account we'll not send the key.
                session["user.auth_userpassword.pwrecover"] = None
                return self.userModule.render.view(
                    skel=None,
                    tpl=self.passwordRecoveryFailedTemplate,
                    reason=self.passwordRecoveryUserNotFound)
            if uSkel["status"] != 10:  # The account is locked or not yet validated. Abort the process
                session["user.auth_userpassword.pwrecover"] = None
                return self.userModule.render.view(
                    skel=None,
                    tpl=self.passwordRecoveryFailedTemplate,
                    reason=self.passwordRecoveryAccountLocked)
            # Update the password, save the user, reset his session and show the success-template
            uSkel["password"] = skel["password"]
            uSkel.toDB()
            session["user.auth_userpassword.pwrecover"] = None
            return self.userModule.render.view(None, tpl=self.passwordRecoverySuccessTemplate)

    @CallDeferred
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
            obj["changedate"] = utcNow()
            db.Put(obj)

        user = db.Query("user").filter("name.idx =", userName).getEntry()
        if user:
            if user.get("changedate") and user["changedate"] > utcNow() - datetime.timedelta(hours=4):
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
            skel["status"] = 2
        else:
            skel["status"] = 10
        skel.toDB()
        return self.userModule.render.view(skel, tpl=self.verifySuccessTemplate)

    def canAdd(self) -> bool:
        return self.registrationEnabled

    def addSkel(self):
        """
            Prepare the add-Skel for rendering.
            Currently only calls self.userModule.addSkel() and sets skel["status"].value depening on
            self.registrationEmailVerificationRequired and self.registrationAdminVerificationRequired
            :return: viur.core.skeleton.Skeleton
        """
        skel = self.userModule.addSkel()
        if self.registrationEmailVerificationRequired:
            defaultStatusValue = 1
        elif self.registrationAdminVerificationRequired:
            defaultStatusValue = 2
        else:  # No further verification required
            defaultStatusValue = 10
        skel.status.readOnly = True
        skel["status"] = defaultStatusValue
        skel.password.required = True  # The user will have to set a password for his account
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
            or not currentRequest.get().isPostRequest  # bail out if not using POST-method
            or not skel.fromClient(kwargs)  # failure on reading into the bones
            or ("bounce" in kwargs and kwargs["bounce"] == "1")):  # review before adding
            # render the skeleton in the version it could as far as it could be read.
            return self.userModule.render.add(skel)
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()
        skel.toDB()
        if self.registrationEmailVerificationRequired and str(skel["status"]) == "1":
            # The user will have to verify his email-address. Create an skey and send it to his address
            skey = securitykey.create(duration=60 * 60 * 24 * 7, userKey=utils.normalizeKey(skel["key"]),
                                      name=skel["name"])
            skel.skey = BaseBone(descr="Skey")
            skel["skey"] = skey
            email.sendEMail(dests=[skel["name"]], tpl=self.userModule.verifyEmailAddressMail, skel=skel)
        self.userModule.onAdded(skel)  # Call onAdded on our parent user module
        return self.userModule.render.addSuccess(skel)


class GoogleAccount(object):
    registrationEnabled = False

    def __init__(self, userModule, modulePath):
        super(GoogleAccount, self).__init__()
        self.userModule = userModule
        self.modulePath = modulePath

    @classmethod
    def getAuthMethodName(*args, **kwargs):
        return u"X-VIUR-AUTH-Google-Account"

    @exposed
    @forceSSL
    def login(self, skey="", token="", *args, **kwargs):
        # FIXME: Check if already logged in
        if not conf.get("viur.user.google.clientID"):
            raise errors.PreconditionFailed("Please configure 'viur.user.google.clientID' in your conf!")
        if not skey or not token:
            currentRequest.get().response.headers["Content-Type"] = "text/html"
            if currentRequest.get().response.headers.get("cross-origin-opener-policy") == "same-origin":
                # We have to allow popups here
                currentRequest.get().response.headers["cross-origin-opener-policy"] = "same-origin-allow-popups"
            # Fixme: Render with Jinja2?
            tplStr = open(os.path.join(utils.coreBasePath,"viur/core/template/vi_user_google_login.html"), "r").read()
            tplStr = tplStr.replace("{{ clientID }}", conf["viur.user.google.clientID"])
            extendCsp({"script-src":["sha256-JpzaUIxV/gVOQhKoDLerccwqDDIVsdn1JclA6kRNkLw="],
                       "style-src":["sha256-FQpGSicYMVC5jxKGS5sIEzrRjSJmkxKPaetUc7eamqc="]})
            return tplStr
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()
        userInfo = id_token.verify_oauth2_token(token, requests.Request(), conf["viur.user.google.clientID"])
        if userInfo['iss'] not in {'accounts.google.com', 'https://accounts.google.com'}:
            raise ValueError('Wrong issuer.')
        # Token looks valid :)
        uid = userInfo['sub']
        email = userInfo['email']
        addSkel = skeletonByKind(self.userModule.addSkel().kindName)  # Ensure that we have the full skeleton
        userSkel = addSkel().all().filter("uid =", uid).getSkel()
        if not userSkel:
            # We'll try again - checking if there's already an user with that email
            userSkel = addSkel().all().filter("name.idx =", email.lower()).getSkel()
            if not userSkel:  # Still no luck - it's a completely new user
                if not self.registrationEnabled:
                    if userInfo.get("hd") and userInfo["hd"] in conf["viur.user.google.gsuiteDomains"]:
                        print("User is from domain - adding account")
                    else:
                        logging.warning("Denying registration of %s", email)
                        raise errors.Forbidden("Registration for new users is disabled")
                userSkel = addSkel()  # We'll add a new user
            userSkel["uid"] = uid
            userSkel["name"] = email
            isAdd = True
        else:
            isAdd = False
        now = utils.utcNow()
        if isAdd or (now - userSkel["lastlogin"]) > datetime.timedelta(minutes=30):
            # Conserve DB-Writes: Update the user max once in 30 Minutes
            userSkel["lastlogin"] = now
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


class TimeBasedOTP(object):
    windowSize = 5
    otpTemplate = "user_login_timebasedotp"

    def __init__(self, userModule, modulePath):
        super(TimeBasedOTP, self).__init__()
        self.userModule = userModule
        self.modulePath = modulePath

    @classmethod
    def get2FactorMethodName(*args, **kwargs):
        return u"X-VIUR-2FACTOR-TimeBasedOTP"

    def canHandle(self, userKey) -> bool:
        user = db.Get(userKey)
        return all(
            [(x in user and (x == "otptimedrift" or bool(user[x]))) for x in ["otpid", "otpkey", "otptimedrift"]])

    def startProcessing(self, userKey):
        user = db.Get(userKey)
        if all([(x in user and user[x]) for x in ["otpid", "otpkey"]]):
            logging.info("OTP wanted for user")
            currentSession.get()["_otp_user"] = {"uid": str(userKey),
                                                 "otpid": user["otpid"],
                                                 "otpkey": user["otpkey"],
                                                 "otptimedrift": user["otptimedrift"],
                                                 "timestamp": time(),
                                                 "failures": 0}
            currentSession.get().markChanged()
            return self.userModule.render.loginSucceeded(msg="X-VIUR-2FACTOR-TimeBasedOTP")

        return None

    class otpSkel(RelSkel):
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

        idx = int(time() / 60.0)  # Current time index
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
        currSess = currentSession.get()
        token = currSess.get("_otp_user")
        if not token:
            raise errors.Forbidden()
        if otptoken is None:
            self.userModule.render.edit(self.otpSkel())
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
            # We got a non-numeric token - this cant be correct
            self.userModule.render.edit(self.otpSkel(), tpl=self.otpTemplate)

        if otptoken in validTokens:
            userKey = currSess["_otp_user"]["uid"]

            del currSess["_otp_user"]
            currSess.markChanged()

            idx = validTokens.index(int(otptoken))

            if abs(idx - self.windowSize) > 2:
                # The time-drift accumulates to more than 2 minutes, update our
                # clock-drift value accordingly
                self.updateTimeDrift(userKey, idx - self.windowSize)

            return self.userModule.secondFactorSucceeded(self, userKey)
        else:
            token["failures"] += 1
            currSess["_otp_user"] = token
            currSess.markChanged()
            return self.userModule.render.edit(self.otpSkel(), loginFailed=True, tpl=self.otpTemplate)

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
        "name": "User",
        "handler": "list",
        "icon": "icon-users"
    }

    def __init__(self, moduleName, modulePath, *args, **kwargs):
        super(User, self).__init__(moduleName, modulePath, *args, **kwargs)

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
        user = utils.getCurrentUser()
        if not (user and user["access"] and ("%s-add" % self.moduleName in user["access"] or "root" in user["access"])):
            skel.status.readOnly = True
            skel["status"] = 0
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
        # Unlock and require a password
        skel.password.required = True
        skel.password.visible = True
        skel.password.readOnly = False
        skel.name.readOnly = False  # Dont enforce readonly name in user/add
        return skel

    def editSkel(self, *args, **kwargs):
        skel = super(User, self).editSkel().clone()

        skel.password = PasswordBone(descr="Passwort", required=False)

        user = utils.getCurrentUser()

        lockFields = not (user and "root" in user["access"])  # If we aren't root, make certain fields read-only
        skel.name.readOnly = lockFields
        skel.access.readOnly = lockFields
        skel.status.readOnly = lockFields

        return skel

    def secondFactorProviderByClass(self, cls):
        return getattr(self, "f2_%s" % cls.__name__.lower())

    def getCurrentUser(self, *args, **kwargs):
        session = currentSession.get()
        if not session:  # May be a deferred task
            return None
        userData = session.get("user")
        if userData:
            skel = self.viewSkel()
            skel.setEntity(userData)
            return skel
        return None

    def continueAuthenticationFlow(self, caller, userKey):
        currSess = currentSession.get()
        currSess["_mayBeUserKey"] = userKey.id_or_name
        currSess["_secondFactorStart"] = utils.utcNow()
        currSess.markChanged()
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
        currSess = currentSession.get()
        logging.debug("Got SecondFactorSucceeded call from %s." % secondFactor)
        if currSess["_mayBeUserKey"] != userKey.id_or_name:
            raise errors.Forbidden()
        # Assert that the second factor verification finished in time
        if utils.utcNow() - currSess["_secondFactorStart"] > self.secondFactorTimeWindow:
            raise errors.RequestTimeout()
        return self.authenticateUser(userKey)

    def authenticateUser(self, userKey: db.Key, **kwargs):
        """
            Performs Log-In for the current session and the given userKey.

            This resets the current session: All fields not explicitly marked as persistent
            by conf["viur.session.persistentFieldsOnLogin"] are gone afterwards.

            :param userKey: The (DB-)Key of the user we shall authenticate
        """
        currSess = currentSession.get()
        res = db.Get(userKey)
        assert res, "Unable to authenticate unknown user %s" % userKey
        oldSession = {k: v for k, v in currSess.items()}  # Store all items in the current session
        currSess.reset()
        # Copy the persistent fields over
        for k in conf["viur.session.persistentFieldsOnLogin"]:
            if k in oldSession:
                currSess[k] = oldSession[k]
        del oldSession
        currSess["user"] = res
        currSess.markChanged()
        currentRequest.get().response.headers["Sec-X-ViUR-StaticSKey"] = currSess.staticSecurityKey
        self.onLogin()
        return self.render.loginSucceeded(**kwargs)

    @exposed
    def logout(self, skey="", *args, **kwargs):
        """
            Implements the logout action. It also terminates the current session (all keys not listed
            in viur.session.persistentFieldsOnLogout will be lost).
        """
        currSess = currentSession.get()
        user = currSess.get("user")
        if not user:
            raise errors.Unauthorized()
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()
        self.onLogout(user)
        oldSession = {k: v for k, v in currSess.items()}  # Store all items in the current session
        currSess.reset()
        # Copy the persistent fields over
        for k in conf["viur.session.persistentFieldsOnLogout"]:
            if k in oldSession:
                currSess[k] = oldSession[k]
        del oldSession
        return self.render.logoutSuccess()

    @exposed
    def login(self, *args, **kwargs):
        authMethods = [(x.getAuthMethodName(), y.get2FactorMethodName() if y else None)
                       for x, y in self.validAuthenticationMethods]
        return self.render.loginChoices(authMethods)

    def onLogin(self):
        usr = self.getCurrentUser()
        logging.info("User logged in: %s" % usr["name"])

    def onLogout(self, usr):
        logging.info("User logged out: %s" % usr["name"])

    @exposed
    def edit(self, *args, **kwargs):
        currSess = currentSession.get()
        if len(args) == 0 and not "key" in kwargs and currSess.get("user"):
            kwargs["key"] = currSess.get("user")["key"]
        return super(User, self).edit(*args, **kwargs)

    @exposed
    def view(self, key, *args, **kwargs):
        """
            Allow a special key "self" to reference always the current user
        """
        if key == "self":
            user = self.getCurrentUser()
            if user:
                return super(User, self).view(str(user["key"].id_or_name), *args, **kwargs)
            else:
                raise errors.Unauthorized()

        return super(User, self).view(key, *args, **kwargs)

    def canView(self, skel) -> bool:
        user = self.getCurrentUser()
        if user:
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

    def onDeleted(self, skel):
        """
            Invalidate all sessions of that user
        """
        super(User, self).onDeleted(skel)
        killSessionByUser(str(skel["key"]))


@StartupTask
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
            addSkel = skeletonByKind(userMod.addSkel().kindName)()  # Ensure we have the full skeleton
            uname = f"""admin@{conf["viur.instance.project_id"]}.appspot.com"""
            pw = utils.generateRandomString(13)
            addSkel["name"] = uname
            addSkel["status"] = 10  # Ensure its enabled right away
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
