# -*- coding: utf-8 -*-
from server.applications.list import List
from server.skeleton import Skeleton, RelSkel
from server import utils, session
from server.bones import *
from server.bones.passwordBone import pbkdf2
from server import errors, conf, securitykey
from server.tasks import StartupTask
from time import time
from server import db
from hashlib import sha512
from itertools import izip
from google.appengine.api import users, app_identity
import logging
import datetime
import hmac, hashlib
import json

class userSkel( Skeleton ):
	kindName = "user"
	enforceUniqueValuesFor = "name", "That E-Mail address is already taken" #Important! Duplicate usernames will cause trouble!
	name = emailBone( descr="E-Mail", required=True, readOnly=True, caseSensitive=False, searchable=True, indexed=True )
	password = passwordBone( descr="Password", required=False, readOnly=True, visible=False )
	access = selectAccessMultiBone( descr="Accessrights", values={"root": "Superuser"}, indexed=True )
	status = selectOneBone( descr="Account status", values = {
				1: "Waiting for EMail verification",
				2: "Waiting for verification through admin",
				5: "Account disabled",
				10: "Active" }, defaultValue="10", required=True, indexed=True )

	# One-Time Password Verification
	otpid = stringBone( descr=u"Serial-Nummer",
	                    required=True,
	                    indexed=True,
	                    searchable=True )

	otpkey = stringBone( descr=u"Hex-Encoded Key",
	                     required=True,
	                     indexed=True )

	otptimedrift = numericBone( descr=u"Zeitkorrektur",
	                            readOnly=True,
	                            defaultValue=0 )



class UserPassword(object):
	registrationEnabled = False
	registrationEmailVerificationRequired = False
	registrationAdminVerificationRequired = False

	def __init__(self, userModule, modulePath):
		super(UserPassword, self).__init__()
		self.userModule = userModule
		self.modulePath = modulePath

	@classmethod
	def getAuthMethodName(*args,**kwargs):
		return (u"X-VIUR-AUTH-User-Password")

	class loginSkel(RelSkel):
		name = emailBone( descr="E-Mail",  required=True, caseSensitive=False, indexed=True )
		password = passwordBone( descr="Password", indexed=True, params={"justinput":True}, required=True )

	def login( self, name=None, password=None, skey="", *args, **kwargs ):
		if self.userModule.getCurrentUser(): #Were already loggedin
			return( self.userModule.render.loginSucceeded( ) )
		if not name or not password or not securitykey.validate( skey ):
			return( self.userModule.render.login( self.loginSkel() ) )
		query = db.Query( self.userModule.viewSkel().kindName )
		res  = query.filter( "name.idx >=", name.lower()).get()
		if res is None:
			res = {"password":"", "status":0, "name":"","name.idx":"" }
		if "password_salt" in res.keys(): #Its the new, more secure passwd
			passwd = pbkdf2( password[ : conf["viur.maxPasswordLength"] ], res["password_salt"] )
		else:
			passwd = sha512( password.encode("UTF-8")+conf["viur.salt"] ).hexdigest()
		isOkay = True
		# We do this exactly that way to avoid timing attacks
		if len( res["password"] ) != len( passwd ):
			isOkay = False
		else:
			for x, y in izip( res["password"], passwd ):
				if x!=y:
					isOkay = False
		if res["status"] < 10:
			isOkay = False
		if res[ "name.idx" ] != name.lower():
			isOkay = False
		if( not isOkay ):
			skel=self.loginSkel()
			skel["name"].fromClient("name",{"name":name} )
			return( self.userModule.render.login( skel, loginFailed=True )  )
		else:
			if not "password_salt" in res.keys(): #Update the password to the new, more secure format
				res[ "password_salt" ] = utils.generateRandomString( 13 )
				res[ "password" ] = pbkdf2( password[ : conf["viur.maxPasswordLength"] ], res["password_salt"] )
				db.Put( res )
			return self.userModule.continueAuthenticationFlow(self, res.key())
	login.exposed = True
	login.forceSSL = True


	def pwrecover( self, authtoken=None, skey=None, *args, **kwargs ):
		if authtoken:
			data = securitykey.validate( authtoken )
			if data and isinstance( data, dict ) and "userid" in data.keys() and "password" in data.keys():
				skel = self.editSkel()
				assert skel.fromDB( data["userid"] )
				skel["password"].value = data["password"]
				skel.toDB()
				return (self.render.view(skel, "user_passwordrecover_success"))
			else:
				return (self.render.view(None, "user_passwordrecover_invalid_token"))
		else:
			skel = self.lostPasswordSkel()
			if len(kwargs)==0 or not skel.fromClient(kwargs):
				return( self.render.passwdRecover( skel, tpl=self.lostPasswordTemplate ) )
			user = self.viewSkel().all().filter( "name.idx =", skel["name"].value.lower() ).get()

			if not user: #Unknown user
				skel.errors["name"] = _("Unknown user")
				return( self.render.passwdRecover( skel, tpl=self.lostPasswordTemplate ) )
			try:
				if user["changedate"]>datetime.datetime.now()-datetime.timedelta(days=1):
					# This user probably has already requested a password reset
					# within the last 24 hrss
					return (self.render.view(skel,
											 "user_passwordrecover_already_sent"))

			except AttributeError: #Some newly generated user-objects dont have such a changedate yet
				pass
			user["changedate"] = datetime.datetime.now()
			db.Put( user )
			key = securitykey.create( 60*60*24, userid=str( user.key() ), password=skel["password"].value )
			self.sendPasswordRecoveryEmail( str( user.key() ), key )
			return (self.render.view(skel, "user_passwordrecover_mail_sent"))
	pwrecover.exposed = True

	def verify(self,  skey,  *args,  **kwargs ):
		data = securitykey.validate( skey )
		skel = self.baseSkel()
		if not data or not isinstance( data,  dict ) or not "userid" in data or not skel.fromDB( data["userid"] ):
			return self.render.verifyFailed()
		if self.registrationAdminVerificationRequired:
			skel["status"].value = 2
		else:
			skel["status"].value = 10
		skel.toDB()
		return self.render.verifySuccess( data )
	verify.exposed = True

	def sendVerificationEmail(self, userID, skey ):
		skel = self.viewSkel()
		assert skel.fromDB(userID)
		skel["skey"] = baseBone( descr="Skey" )
		skel["skey"].value = skey
		utils.sendEMail( [skel["name"].value], self.verifyEmailAddressMail, skel )

	def sendPasswordRecoveryEmail(self, userID, skey ):
		skel = self.viewSkel()
		assert skel.fromDB(userID)
		skel["skey"] = baseBone( descr="Skey" )
		skel["skey"].value = skey
		utils.sendEMail( [skel["name"].value], self.passwordRecoveryMail, skel )


class GoogleAccount(object):

	def __init__(self, userModule, modulePath):
		super(GoogleAccount, self).__init__()
		self.userModule = userModule
		self.modulePath = modulePath

	@classmethod
	def getAuthMethodName(*args,**kwargs):
		return (u"X-VIUR-AUTH-Google-Account")

	def login( self, skey="", *args, **kwargs ):
		def updateCurrentUser():
			currentUser = users.get_current_user()
			uid = currentUser.user_id()
			mysha512 = sha512()
			mysha512.update( str(uid)+conf["viur.salt"]  )
			uidHash = mysha512.hexdigest()

			user = db.GetOrInsert( "user-%s" % uidHash, kindName=self.userModule.viewSkel().kindName, uid=uid, name=currentUser.email(), creationdate=datetime.datetime.now(), access=None )
			#Update the user
			dt = datetime.datetime.now()
			if (not "lastlogin" in user.keys()) or (dt-user["lastlogin"])>datetime.timedelta( minutes=30 ):
				#Save DB-Writes: Update the user max once in 30 Minutes
				user["lastlogin"] = dt
				if users.is_current_user_admin():
					try:
						if not "root" in user.access:
							user["access"].append("root")
					except:
						user["access"] = ["root"]
					user["gaeadmin"] = 1
				else:
					user["gaeadmin"] = 0
				db.Put( user )
			return user
		if users.get_current_user():
			user = db.RunInTransaction( updateCurrentUser )
			return self.userModule.continueAuthenticationFlow(self, user.key())
		else:
			raise( errors.Redirect( users.create_login_url( self.modulePath+"/login") ) )
	login.exposed = True
	login.forceSSL = True

class Otp2Factor( object ):
	def __init__(self, userModule, modulePath):
		super(Otp2Factor, self).__init__()
		self.userModule = userModule
		self.modulePath = modulePath

	@classmethod
	def get2FactorMethodName(*args,**kwargs):
		return (u"X-VIUR-2Factor-Otp")

	def canHandle(self, userId):
		user = db.Get(userId)
		return all([(x in user.keys() and user[x]) for x in ["otpid", "otpkey", "otptimedrift"]])


	def startProcessing(self, userId):
		user = db.Get(userId)
		if all([(x in user.keys() and user[x]) for x in ["otpid", "otpkey", "otptimedrift"]]):
			logging.info( "OTP wanted for user" )
			session.current["_otp_user"] = {	"uid": str(userId),
								"otpid": user["otpid"],
								"otpkey": user["otpkey"],
								"otptimedrift": user["otptimedrift"],
								"timestamp": time() }
			session.current.markChanged()
			return self.userModule.render.loginSucceeded()
		return None

	class otpSkel( RelSkel ):
		otptoken = stringBone( descr="Token", required=True, caseSensitive=False, indexed=True )

	def generateOtps(self, secret, window=5):
		"""
			Generates all valid tokens for the given secret
		"""
		def asBytes( valIn):
			"""
				Returns the integer in binary representation
			"""
			hexStr = hex( valIn )[2:]
			#Maybe uneven length
			if len(hexStr)%2==1:
				hexStr = "0"+hexStr
			return( ("00"*(8-(len(hexStr)/2))+hexStr).decode("hex") )

		idx = int( time()/60.0 ) # Current time index
		res = []
		for slot in range( idx-window, idx+window ):
			currHash= hmac.new( secret.decode("HEX"), asBytes(slot), hashlib.sha1 ).digest()
			# Magic code from https://tools.ietf.org/html/rfc4226 :)
			offset = ord(currHash[19]) & 0xf
			code = ((ord(currHash[offset]) & 0x7f) << 24 |
				(ord(currHash[offset + 1]) & 0xff) << 16 |
				(ord(currHash[offset + 2]) & 0xff) << 8 |
				(ord(currHash[offset + 3]) & 0xff))
			res.append( int( str(code)[-6: ])) #We use only the last 6 digits
		return res

	def otp(self, otptoken=None, skey=None, *args, **kwargs ):
		token = session.current.get("_otp_user")
		if not token:
			raise errors.Forbidden()

		if not otptoken or not skey:
			return( self.userModule.render.edit( self.otpSkel(), otpFailed=False, tpl="user_otp"  ) )

		validTokens = self.generateOtps( token["otpkey"] )
		logging.debug( int( otptoken ) )
		logging.debug( validTokens )
		logging.debug( int( otptoken ) in validTokens )

		if int(otptoken) in validTokens:
			userId = session.current["_otp_user"]["uid"]
			del session.current["_otp_user" ]
			session.current.markChanged()
			return self.userModule.secondFactorSucceeded(self, userId)
		else:
			return self.render.edit( self.otpSkel(), otpFailed=True, tpl="user_otp"  )
	otp.exposed = True
	otp.forceSSL = True

class User(List):
	kindName = "user"
	addTemplate = "user_add"
	addSuccessTemplate = "user_add_success"
	lostPasswordTemplate = "user_lostpassword"
	verifyEmailAddressMail = "user_verify_address"
	passwordRecoveryMail = "user_password_recovery"

	authenticationProviders = [UserPassword,GoogleAccount]
	secondFactorProviders = [Otp2Factor]

	validAuthenticationMethods = [(UserPassword,Otp2Factor),(UserPassword,None)]

	
	adminInfo = {	"name": "User", #Name of this modul, as shown in ViUR Admin (will be translated at runtime)
				"handler": "list",  #Which handler to invoke
				"icon": "icons/modules/users.svg", #Icon for this modul
				}

	def __init__(self, modulName, modulPath, *args, **kwargs):
		super(User, self).__init__(modulName, modulPath, *args, **kwargs)

		# Initialize the payment-providers
		self.initializedAuthenticationProviders = {}
		self.initializedSecondFactorProviders = {}

		for p in self.authenticationProviders:
			pInstance = p(self, modulPath+"/auth_%s" % p.__name__.lower())
			self.initializedAuthenticationProviders[pInstance.__class__.__name__.lower()] = pInstance
			#Also put it as an object into self, sothat any exposed function is reachable
			setattr( self, "auth_%s" % pInstance.__class__.__name__.lower(), pInstance )
			logging.error("auth_%s" % pInstance.__class__.__name__.lower() )


		for p in self.secondFactorProviders:
			pInstance = p(self, modulPath+"/f2_%s" % p.__name__.lower())
			self.initializedAuthenticationProviders[pInstance.__class__.__name__.lower()] = pInstance
			#Also put it as an object into self, sothat any exposed function is reachable
			setattr( self, "f2_%s" % pInstance.__class__.__name__.lower(), pInstance )
			logging.error("f2_%s" % pInstance.__class__.__name__.lower() )

	def secondFactorProviderByClass(self, cls):
		return getattr(self, "f2_%s" % cls.__name__.lower())

	def getCurrentUser( self, *args, **kwargs ):
		return( session.current.get("user") )

	def continueAuthenticationFlow(self, caller, userId):
		for authProvider, secondFactor in self.validAuthenticationMethods:
			if secondFactor is None:
				# We allow sign-in without a second factor
				return self.authenticateUser(userId)
			if isinstance(caller,authProvider):
				# This Auth-Request was issued from this authenticationProvider
				secondFactorProvider = self.secondFactorProviderByClass(secondFactor)
				if secondFactorProvider.canHandle(userId):
					# We choose the first second factor provider which claims it can verify that user
					return secondFactor.startProcessing(userId)
		# Whoops.. This user logged in successfully - but we have no second factor provider willing to confirm it
		raise errors.NotAcceptable("There are no more authentication methods to try") # Sorry...

	def authenticateUser(self, userId):
		"""
			Performs Log-In for the current session and the given userId.
			This resets the current session: All fields not explicitly marked as persistent
			by conf["viur.session.persistentFieldsOnLogin"] are gone afterwards.

			:param authProvider: Which authentication-provider issued the authenticateUser request
			:type authProvider: object
			:param userId: The (DB-)Key of the user we shall authenticate
			:type userId: db.Key
		"""
		res = db.Get(userId)
		assert res, "Unable to authenticate unknown user %s" % userId

		oldSession = {k:v for k,v in session.current.items()} #Store all items in the current session
		session.current.reset()
		# Copy the persistent fields over
		for k in conf["viur.session.persistentFieldsOnLogin"]:
			if k in oldSession.keys():
				session.current[ k ] = oldSession[ k ]
		del oldSession
		session.current['user'] = {}
		for key in ["name", "status", "access"]:
			try:
				session.current['user'][ key ] = res[ key ]
			except: pass
		session.current['user']["id"] = str( res.key() )
		if not "access" in session.current['user'].keys() or not session.current['user']["access"]:
			session.current['user']["access"] = []
		session.current.markChanged()
		self.onLogin()
		logging.error("Calling: self.render.loginSucceeded( )")
		return( self.render.loginSucceeded( ) )

	def logout( self,  skey="", *args,  **kwargs ): #fixme
		user = session.current.get("user")
		if not user:
			raise errors.Unauthorized()
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		session.current["user"] = None
		return self.render.logoutSuccess( )
	logout.exposed = True

	def login(self,*args,**kwargs):
		self.render.login(self.validAuthenticationMethods)
	login.exposed=True

	def edit( self,  *args,  **kwargs ):
		if len( args ) == 0 and not "id" in kwargs and session.current.get("user"):
			kwargs["id"] = session.current.get("user")["id"]
		return( super( User, self ).edit( *args,  **kwargs ) )
	edit.exposed=True

	def view(self, id, *args, **kwargs):
		"""
			Allow a special id "self" to reference always the current user
		"""
		if id=="self":
			user = self.getCurrentUser()
			if user:
				return( super( User, self ).view( user["id"], *args, **kwargs ) )
		return( super( User, self ).view( id, *args, **kwargs ) )
	view.exposed=True

	def canView(self, skel):
		user = self.getCurrentUser()
		if user:
			if skel["id"].value==user["id"]:
				return( True )
			if "root" in user["access"] or "user-view" in user["access"]:
				return( True )
		return( False )

	def getAuthMethod( self, *args, **kwargs ):
		"""Inform tools like Viur-Admin which authentication to use"""
		res=[]
		for auth,secondFactor in self.validAuthenticationMethods:
			res.append(auth.getAuthMethodName())
		return( json.dumps(res) )
	getAuthMethod.exposed = True

	
	def onItemDeleted( self, skel ):
		"""
			Invalidate all sessions of that user
		"""
		super( User, self ).onItemDeleted( skel )
		session.killSessionByUser( str( skel["id"].value ) )



@StartupTask
def createNewUserIfNotExists():
	"""
		Create a new Admin user, if the userDB is empty
	"""
	if "user" in dir( conf["viur.mainApp"] ):# We have a user module
		userMod = getattr( conf["viur.mainApp"], "user" )
		if isinstance( userMod, User ) and "addSkel" in dir(userMod): #Its our user module :)
			if not db.Query( userMod.addSkel().kindName ).get(): #There's currently no user in the database
				l = userMod.addSkel()
				l["password"] = passwordBone( descr="Password", required=True )
				uname = "admin@%s.appspot.com" % app_identity.get_application_id()
				pw = utils.generateRandomString( 13 )
				l.setValues( {	"name":uname,
						"status": 10,
						"access": ["root"] } )
				l["password"].value = pw
				try:
					l.toDB()
				except:
					return
				logging.warn("Created a new adminuser for you! Username: %s, Password: %s" % (uname,pw) )
				utils.sendEMailToAdmins( "Your new ViUR password", "ViUR created a new adminuser for you! Username: %s, Password: %s" % (uname,pw) )
