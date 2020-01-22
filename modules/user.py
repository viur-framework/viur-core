# -*- coding: utf-8 -*-
from viur.core.prototypes.list import List
from viur.core.skeleton import Skeleton, RelSkel, skeletonByKind
from viur.core import utils, session, request
from viur.core.bones import *
from viur.core.bones.bone import UniqueValue, UniqueLockMethod
from viur.core.bones.passwordBone import pbkdf2
from viur.core import errors, conf, securitykey
from viur.core.tasks import StartupTask
from time import time
from viur.core import db, exposed, forceSSL
from hashlib import sha512
#from google.appengine.api import users, app_identity
import logging
import datetime
import hmac, hashlib
import json
from google.oauth2 import id_token
from google.auth.transport import requests
from viur.core.i18n import translate

class userSkel(Skeleton):
	kindName = "user"

	# Properties required by google and custom auth
	name = emailBone(
		descr=u"E-Mail",
		required=True,
		readOnly=True,
		caseSensitive=False,
		searchable=True,
		indexed=True,
		unique=UniqueValue(UniqueLockMethod.SameValue, "Username already taken")
	)

	# Properties required by custom auth
	password = passwordBone(
		descr=u"Password",
		required=False,
		readOnly=True,
		visible=False
	)

	# Properties required by google auth
	uid = stringBone(
		descr=u"Google's UserID",
		indexed=True,
		required=False,
		readOnly=True,
		unique=UniqueValue(UniqueLockMethod.SameValue, "UID already in use")
	)
	gaeadmin = booleanBone(
		descr=u"Is GAE Admin",
		defaultValue=False,
		readOnly=True
	)

	# Generic properties
	access = selectAccessBone(
		descr=u"Access rights",
		values={"root": "Superuser"},
		indexed=True
	)
	status = selectBone(
		descr=u"Account status",
		values={
			1: u"Waiting for email verification",
			2: u"Waiting for verification through admin",
			5: u"Account disabled",
			10: u"Active"
		},
		defaultValue="10",
		required=True,
		indexed=True
	)
	lastlogin = dateBone(
		descr=u"Last Login",
		readOnly=True,
		indexed=True
	)

	# One-Time Password Verification
	otpid = stringBone(
		descr=u"OTP serial",
		required=False,
		indexed=True,
		searchable=True
	)
	otpkey = credentialBone(
		descr=u"OTP hex key",
		required=False,
		indexed=True
	)
	otptimedrift = numericBone(
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

	def __init__(self, userModule, modulePath):
		super(UserPassword, self).__init__()
		self.userModule = userModule
		self.modulePath = modulePath

	@classmethod
	def getAuthMethodName(*args, **kwargs):
		return u"X-VIUR-AUTH-User-Password"

	class loginSkel(RelSkel):
		name = emailBone(descr="E-Mail", required=True, caseSensitive=False, indexed=True)
		password = passwordBone(descr="Password", indexed=True, params={"justinput": True}, required=True)

	class lostPasswordSkel(RelSkel):
		name = stringBone(descr="username", required=True)
		password = passwordBone(descr="New Password", required=True)

	@exposed
	@forceSSL
	def login(self, name=None, password=None, skey="", *args, **kwargs):
		if self.userModule.getCurrentUser():  # Were already logged in
			return self.userModule.render.loginSucceeded()

		if not name or not password or not securitykey.validate(skey, useSessionKey=True):
			return self.userModule.render.login(self.loginSkel())

		query = db.Query(self.userModule.viewSkel().kindName)
		res = query.filter("name_idx >=", name.lower()).get()

		if res is None:
			res = {"password": {"pwhash": "-invalid-", "salt": "-invalid"}, "status": 0, "name": "", "name.idx": ""}

		passwd = pbkdf2(password[:conf["viur.maxPasswordLength"]], (res.get("password", None) or {}).get("salt", ""))
		isOkay = True

		# We do this exactly that way to avoid timing attacks

		# Check if the username matches
		storedUserName = res.get("name_idx", "")
		if len(storedUserName) != len(name.lower()):
			isOkay = False
		else:
			for x, y in zip(storedUserName, name.lower()):
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

		# Verify that this account isn't blocked
		if res["status"] < 10:
			isOkay = False

		if not isOkay:
			skel = self.loginSkel()
			skel.fromClient({"name": name, "nomissing": "1"})
			return self.userModule.render.login(skel, loginFailed=True)
		else:
			return self.userModule.continueAuthenticationFlow(self, res.key)

	@exposed
	def pwrecover(self, authtoken=None, skey=None, *args, **kwargs):
		if authtoken:
			data = securitykey.validate(authtoken, useSessionKey=False)
			if data and isinstance(data, dict) and "userKey" in data and "password" in data:
				skel = self.userModule.editSkel()
				assert skel.fromDB(data["userKey"])
				skel["password"] = data["password"]
				skel.toDB()
				return self.userModule.render.view(skel, self.passwordRecoverySuccessTemplate)
			else:
				return self.userModule.render.view(None, self.passwordRecoveryInvalidTokenTemplate)
		else:
			skel = self.lostPasswordSkel()
			if len(kwargs) == 0 or not skel.fromClient(kwargs) or not securitykey.validate(skey, useSessionKey=True):
				return self.userModule.render.passwdRecover(skel, tpl=self.passwordRecoveryTemplate)
			user = self.userModule.viewSkel().all().filter("name.idx =", skel["name"].lower()).get()

			if not user or user["status"] < 10:  # Unknown user or locked account
				skel.errors["name"] = str("Unknown user")
				return self.userModule.render.passwdRecover(skel, tpl=self.passwordRecoveryTemplate)
			try:
				if user["changedate"] > (datetime.datetime.now() - datetime.timedelta(days=1)):
					# This user probably has already requested a password reset
					# within the last 24 hrss
					return self.userModule.render.view(skel, self.passwordRecoveryAlreadySendTemplate)

			except AttributeError:  # Some newly generated user-objects dont have such a changedate yet
				pass
			user["changedate"] = datetime.datetime.now()
			db.Put(user)
			userSkel = self.userModule.viewSkel().ensureIsCloned()
			assert userSkel.fromDB(user.key())
			userSkel.skey = baseBone(descr="Skey")
			userSkel["skey"] = securitykey.create(60 * 60 * 24, userKey=str(user.key()), password=skel["password"])
			utils.sendEMail([userSkel["name"]], self.userModule.passwordRecoveryMail, userSkel)
			return self.userModule.render.view({}, self.passwordRecoveryInstuctionsSendTemplate)

	@exposed
	def verify(self, skey, *args, **kwargs):
		data = securitykey.validate(skey, useSessionKey=False)
		skel = self.userModule.baseSkel()
		if not data or not isinstance(data, dict) or not "userKey" in data or not skel.fromDB(data["userKey"]):
			return self.userModule.render.view(None, self.verifyFailedTemplate)
		if self.registrationAdminVerificationRequired:
			skel["status"] = 2
		else:
			skel["status"] = 10
		skel.toDB()
		return self.userModule.render.view(skel, self.verifySuccessTemplate)

	def canAdd(self):
		return self.registrationEnabled

	def addSkel(self):
		"""
			Prepare the add-Skel for rendering.
			Currently only calls self.userModule.addSkel() and sets skel["status"].value depening on
			self.registrationEmailVerificationRequired and self.registrationAdminVerificationRequired
			:return: server.skeleton.Skeleton
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

			.. seealso:: :func:`addSkel`, :func:`onItemAdded`, :func:`canAdd`

			:returns: The rendered, added object of the entry, eventually with error hints.

			:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
			:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if not self.canAdd():
			raise errors.Unauthorized()
		skel = self.addSkel()
		if (len(kwargs) == 0  # no data supplied
				or skey == ""  # no skey supplied
				or not request.current.get().isPostRequest  # bail out if not using POST-method
				or not skel.fromClient(kwargs)  # failure on reading into the bones
				or ("bounce" in kwargs and kwargs["bounce"] == "1")):  # review before adding
			# render the skeleton in the version it could as far as it could be read.
			return self.userModule.render.add(skel)
		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()
		skel.toDB()
		if self.registrationEmailVerificationRequired and str(skel["status"]) == "1":
			# The user will have to verify his email-address. Create an skey and send it to his address
			skey = securitykey.create(duration=60 * 60 * 24 * 7, userKey=str(skel["key"]), name=skel["name"])
			skel.skey = baseBone(descr="Skey")
			skel["skey"] = skey
			utils.sendEMail([skel["name"]], self.userModule.verifyEmailAddressMail, skel)
		self.userModule.onItemAdded(skel)  # Call onItemAdded on our parent user module
		return self.userModule.render.addItemSuccess(skel)


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
			raise errors.PreconditionFailed()
		if not skey or not token:
			request.current.get().response.headers["Content-Type"] = "text/html"
			# Fixme: Render with Jinja2?
			tplStr = open("server/template/vi_user_google_login.html", "r").read()
			tplStr = tplStr.replace("{{ clientID }}", conf["viur.user.google.clientID"])
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
		now = datetime.datetime.now()
		if isAdd or (now - userSkel["lastlogin"]) > datetime.timedelta(minutes=30):
			# Conserve DB-Writes: Update the user max once in 30 Minutes
			userSkel["lastlogin"] = now
			#if users.is_current_user_admin():
			#	if not userSkel["access"]:
			#		userSkel["access"] = []
			#	if not "root" in userSkel["access"]:
			#		userSkel["access"].append("root")
			#	userSkel["gaeadmin"] = True
			#else:
			#	userSkel["gaeadmin"] = False
			assert userSkel.toDB()
		return self.userModule.continueAuthenticationFlow(self, (userSkel.kindName, userSkel["key"]))

		if users.get_current_user():

			currentUser = users.get_current_user()
			uid = currentUser.user_id()

		raise errors.Redirect(users.create_login_url(self.modulePath + "/login"))


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

	def canHandle(self, userKey):
		user = db.Get(userKey)
		return all(
			[(x in user and (x == "otptimedrift" or bool(user[x]))) for x in ["otpid", "otpkey", "otptimedrift"]])

	def startProcessing(self, userKey):
		user = db.Get(userKey)
		if all([(x in user and user[x]) for x in ["otpid", "otpkey"]]):
			logging.info("OTP wanted for user")
			session.current["_otp_user"] = {"uid": str(userKey),
											"otpid": user["otpid"],
											"otpkey": user["otpkey"],
											"otptimedrift": user["otptimedrift"],
											"timestamp": time(),
											"failures": 0}
			session.current.markChanged()
			return self.userModule.render.loginSucceeded(msg="X-VIUR-2FACTOR-TimeBasedOTP")

		return None

	class otpSkel(RelSkel):
		otptoken = stringBone(descr="Token", required=True, caseSensitive=False, indexed=True)

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
			return (("00" * (8 - (len(hexStr) / 2)) + hexStr).decode("hex"))

		idx = int(time() / 60.0)  # Current time index
		idx += int(timeDrift)
		res = []
		for slot in range(idx - self.windowSize, idx + self.windowSize):
			currHash = hmac.new(secret.decode("HEX"), asBytes(slot), hashlib.sha1).digest()
			# Magic code from https://tools.ietf.org/html/rfc4226 :)
			offset = ord(currHash[19]) & 0xf
			code = ((ord(currHash[offset]) & 0x7f) << 24 |
					(ord(currHash[offset + 1]) & 0xff) << 16 |
					(ord(currHash[offset + 2]) & 0xff) << 8 |
					(ord(currHash[offset + 3]) & 0xff))
			res.append(int(str(code)[-6:]))  # We use only the last 6 digits
		return res

	@exposed
	@forceSSL
	def otp(self, otptoken=None, skey=None, *args, **kwargs):
		token = session.current.get("_otp_user")
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
			userKey = session.current["_otp_user"]["uid"]

			del session.current["_otp_user"]
			session.current.markChanged()

			idx = validTokens.index(int(otptoken))

			if abs(idx - self.windowSize) > 2:
				# The time-drift accumulates to more than 2 minutes, update our
				# clock-drift value accordingly
				self.updateTimeDrift(userKey, idx - self.windowSize)

			return self.userModule.secondFactorSucceeded(self, userKey)
		else:
			token["failures"] += 1
			session.current["_otp_user"] = token
			session.current.markChanged()
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
		"icon": "icons/modules/users.svg"
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

	def extendAccessRights(self, skel):
		accessRights = skel.access.values.copy()
		for right in conf["viur.accessRights"]:
			accessRights[right] = translate("server.modules.user.accessright.%s" % right, defaultText=right)
		skel.access.values = accessRights

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
			self.extendAccessRights(skel)
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
		self.extendAccessRights(skel)

		skel.password = passwordBone(descr="Passwort", required=False)

		user = utils.getCurrentUser()

		lockFields = not (user and "root" in user["access"])  # If we aren't root, make certain fields read-only
		skel.name.readOnly = lockFields
		skel.access.readOnly = lockFields
		skel.status.readOnly = lockFields

		return skel

	def secondFactorProviderByClass(self, cls):
		return getattr(self, "f2_%s" % cls.__name__.lower())

	def getCurrentUser(self, *args, **kwargs):
		#usr = session.current.get("user")
		#if not usr:
		#	session.current["user"] = {"name": "test@adm.de", "access": ["root"], "key": "VektIwimKhgWD2dBp10m"}
		return session.current.get("user")

	def continueAuthenticationFlow(self, caller, userKey):
		session.current["_mayBeUserKey"] = str(userKey)
		session.current["_secondFactorStart"] = datetime.datetime.now()
		session.current.markChanged()
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
		logging.debug("Got SecondFactorSucceeded call from %s." % secondFactor)

		if str(session.current["_mayBeUserKey"]) != str(userKey):
			raise errors.Forbidden()
		# Assert that the second factor verification finished in time
		if datetime.datetime.now() - session.current["_secondFactorStart"] > self.secondFactorTimeWindow:
			raise errors.RequestTimeout()

		return self.authenticateUser(userKey)

	def authenticateUser(self, userKey, **kwargs):
		"""
			Performs Log-In for the current session and the given userKey.

			This resets the current session: All fields not explicitly marked as persistent
			by conf["viur.session.persistentFieldsOnLogin"] are gone afterwards.

			:param authProvider: Which authentication-provider issued the authenticateUser request
			:type authProvider: object
			:param userKey: The (DB-)Key of the user we shall authenticate
			:type userKey: db.Key
		"""
		res = db.Get(userKey)
		assert res, "Unable to authenticate unknown user %s" % userKey

		oldSession = {k: v for k, v in session.current.items()}  # Store all items in the current session
		session.current.reset()

		# Copy the persistent fields over
		for k in conf["viur.session.persistentFieldsOnLogin"]:
			if k in oldSession:
				session.current[k] = oldSession[k]

		del oldSession
		session.current["user"] = {}

		for key in ["name", "status", "access"]:
			try:
				session.current["user"][key] = res[key]
			except:
				pass

		session.current["user"]["key"] = userKey
		if not "access" in session.current["user"] or not session.current["user"]["access"]:
			session.current["user"]["access"] = []

		session.current.markChanged()
		request.current.get().response.headers["Sec-X-ViUR-StaticSKey"] = session.current.session.staticSecurityKey
		self.onLogin()

		return self.render.loginSucceeded(**kwargs)

	@exposed
	def logout(self, skey="", *args, **kwargs):
		"""
			Implements the logout action. It also terminates the current session (all keys not listed
			in viur.session.persistentFieldsOnLogout will be lost).
		"""
		user = session.current.get("user")
		if not user:
			raise errors.Unauthorized()
		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()

		self.onLogout(user)

		oldSession = {k: v for k, v in session.current.items()}  # Store all items in the current session
		session.current.reset()

		# Copy the persistent fields over
		for k in conf["viur.session.persistentFieldsOnLogout"]:
			if k in oldSession:
				session.current[k] = oldSession[k]

		del oldSession

		return self.render.logoutSuccess()

	@exposed
	def login(self, *args, **kwargs):
		authMethods = [(x.getAuthMethodName(), y.get2FactorMethodName() if y else None)
					   for x, y in self.validAuthenticationMethods]

		return self.render.login(authMethods)

	def onLogin(self):
		usr = self.getCurrentUser()
		logging.info("User logged in: %s" % usr["name"])

	def onLogout(self, usr):
		logging.info("User logged out: %s" % usr["name"])

	@exposed
	def edit(self, *args, **kwargs):
		if len(args) == 0 and not "key" in kwargs and session.current.get("user"):
			kwargs["key"] = session.current.get("user")["key"]

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

	def canView(self, skel):
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

	def onItemDeleted(self, skel):
		"""
			Invalidate all sessions of that user
		"""
		super(User, self).onItemDeleted(skel)
		session.killSessionByUser(str(skel["key"]))


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
			and any([x[0] is UserPassword for x in userMod.validAuthenticationMethods])):  # It uses UserPassword login
		if not db.Query(userMod.addSkel().kindName).get():  # There's currently no user in the database
			addSkel = skeletonByKind(userMod.addSkel().kindName)()  # Ensure we have the full skeleton
			uname = "admin@%s.appspot.com" % utils.projectID
			pw = utils.generateRandomString(13)
			addSkel["name"] = uname
			addSkel["status"] = 10  # Ensure its enabled right away
			addSkel["access"] = ["root"]
			addSkel["password"] = pw
			try:
				addSkel.toDB()
			except Exception as e:
				logging.error("Something went wrong when trying to add admin user %s with Password %s", (uname, pw))
				logging.exception(e)
				return
			logging.warning("ViUR created a new admin-user for you! Username: %s, Password: %s" % (uname, pw))
			utils.sendEMailToAdmins("Your new ViUR password",
									"ViUR created a new admin-user for you! Username: %s, Password: %s" % (uname, pw))
