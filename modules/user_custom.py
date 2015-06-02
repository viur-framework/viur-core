# -*- coding: utf-8 -*-
from server.applications.list import List
from server.skeleton import Skeleton
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


class CustomUser( List ):
	kindName = "user"
	addTemplate = "user_add"
	addSuccessTemplate = "user_add_success"
	lostPasswordTemplate = "user_lostpassword"
	verifyEmailAddressMail = "user_verify_address"
	passwordRecoveryMail = "user_password_recovery"
	
	def addUser(self, name, password ):
		raise NotImplementedError() #Fixme: Dont use! Doesn't wirte uniquePropertyIndex
		skel = self.loginSkel()
		salt = utils.generateRandomString(13)
		pwHash = pbkdf2( password[ : conf["viur.maxPasswordLength"] ], salt )
		uidHash = sha512( name.lower().encode("utf-8")+conf["viur.salt"] ).hexdigest()
		return( db.GetOrInsert( uidHash,
					kindName=skel["kindName"],
					name=name,
					name_idx=name.lower(),
					password=pwHash,
					password_salt = salt,
					creationdate=datetime.datetime.now() ) )

	def getAuthMethod( self, *args, **kwargs ):
		"""Inform tools like Viur-Admin which authentication to use"""
		return( "X-VIUR-INTERNAL" )
	getAuthMethod.exposed = True	
	
	class loginSkel( Skeleton ):
		kindName = "user"
		id = None
		name = emailBone( descr="E-Mail",  required=True, caseSensitive=False, indexed=True )
		password = passwordBone( descr="Password", indexed=True, params={"justinput":True}, required=True )

	def addSkel( self ):
		admin=False
		skel = super(CustomUser, self).addSkel()
		#Check the GAE API
		if users.is_current_user_admin():
			admin=True
		if "user" in dir( conf["viur.mainApp"] ): #Check for our custom user-api
			user = conf["viur.mainApp"].user.getCurrentUser()
			if user and user["access"] and ("%s-add" % self.modulName in user["access"] or "root" in user["access"] ):
				admin=True
		if not admin:
			if self.registrationEmailVerificationRequired:
				defaultStatusValue = 1
				#skey = securitykey.create( duration=60*60*24*7 , userid=str(newUser.key()), name=skel["name"].value )
				#self.sendVerificationEmail( str(newUser.key()), skey )
			elif self.registrationAdminVerificationRequired:
				defaultStatusValue = 2
			else: #No further verification required
				defaultStatusValue = 10
			skel["status"].readOnly = True
			skel["status"].value = defaultStatusValue
			skel["status"].visible = False
			#= baseBone( defaultValue=defaultStatusValue, readOnly=True, visible=False )
			skel["access"].readOnly = True
			skel["access"].value = []
			skel["access"].visible = False
		else:
			accessRights = skel["access"].values.copy()
			for right in conf["viur.accessRights"]:
				accessRights[ right ] = _( right )
			skel["access"].values = accessRights
		skel["name"].readOnly = False #Dont enforce readonly name in user/add
		skel["password"] = passwordBone( descr="Password", required=True )
		return( skel )

	def editSkel( self, *args,  **kwargs ):
		skel = super(CustomUser, self).editSkel()
		accessRights = skel["access"].values.copy()
		for right in conf["viur.accessRights"]:
			accessRights[ right ] = _( right )
		skel["access"].values = accessRights
		skel["password"] = passwordBone( descr="Passwort", required=False )
		currUser = utils.getCurrentUser()
		if currUser and "root" in currUser["access"]:
			skel["name"].readOnly=False
		return( skel )

	class lostPasswordSkel( Skeleton ):
		kindName = "user"
		name = stringBone( descr="username", required=True )
		password = passwordBone( descr="New Password", required=True )
	

	registrationEnabled = True
	registrationEmailVerificationRequired = True
	registrationAdminVerificationRequired = False
	
	adminInfo = {	"name": "User", #Name of this modul, as shown in ViUR Admin (will be translated at runtime)
				"handler": "list",  #Which handler to invoke
				"icon": "icons/modules/users.svg", #Icon for this modul
				}
	
	def getCurrentUser( self, *args, **kwargs ):
		return( session.current.get("user") )
	
	def canAdd(self):
		if self.registrationEnabled:
			return( True )
		return( super( CustomUser, self ).canAdd() )


	def login( self, name=None, password=None, skey="", *args, **kwargs ):
		if self.getCurrentUser(): #Were already loggedin
			return( self.render.loginSucceeded( ) )
		if not name or not password or not securitykey.validate( skey ):
			return( self.render.login( self.loginSkel() ) )
		query = db.Query( self.viewSkel().kindName )
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
			return( self.render.login( skel, loginFailed=True )  )
		else:
			if not "password_salt" in res.keys(): #Update the password to the new, more secure format
				res[ "password_salt" ] = utils.generateRandomString( 13 )
				res[ "password" ] = pbkdf2( password[ : conf["viur.maxPasswordLength"] ], res["password_salt"] )
				db.Put( res )
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
			return( self.render.loginSucceeded( ) )
	login.exposed = True
	login.forceSSL = True
	
	def logout( self,  skey="", *args,  **kwargs ): #fixme
		user = session.current.get("user")
		if not user:
			raise errors.Unauthorized()
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		session.current["user"] = None
		return self.render.logoutSuccess( )
	logout.exposed = True
	login.forceSSL = True

	def edit( self,  *args,  **kwargs ):
		if len( args ) == 0 and not "id" in kwargs and session.current.get("user"):
			kwargs["id"] = session.current.get("user")["id"]
		return( super( CustomUser, self ).edit( *args,  **kwargs ) )
	edit.exposed=True

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

	def view(self, id, *args, **kwargs):
		"""
			Allow a special id "self" to reference always the current user
		"""
		if id=="self":
			user = self.getCurrentUser()
			if user:
				return( super( CustomUser, self ).view( user["id"], *args, **kwargs ) )
		return( super( CustomUser, self ).view( id, *args, **kwargs ) )
	view.exposed=True

	def canView(self, skel):
		user = self.getCurrentUser()
		if user:
			if skel["id"].value==user["id"]:
				return( True )
			if "root" in user["access"] or "user-view" in user["access"]:
				return( True )
		return( False )
	
	def onItemAdded( self, skel ):
		"""
			Ensure that the verifyEmailAddressMail get's send if needed.
		"""
		super( CustomUser, self ).onItemAdded( skel )
		if self.registrationEmailVerificationRequired and str(skel["status"].value)=="1":
			skey = securitykey.create( duration=60*60*24*7 , userid=str(skel["id"].value), name=skel["name"].value )
			self.sendVerificationEmail( str(skel["id"].value), skey )
	
	def onItemDeleted( self, skel ):
		"""
			Invalidate all sessions of that user
		"""
		super( CustomUser, self ).onItemDeleted( skel )
		session.killSessionByUser( str( skel["id"].value ) )



@StartupTask
def createNewUserIfNotExists():
	"""
		Create a new Admin user, if the userDB is empty
	"""
	if "user" in dir( conf["viur.mainApp"] ):# We have a user module
		userMod = getattr( conf["viur.mainApp"], "user" )
		if isinstance( userMod, CustomUser ) and "loginSkel" in dir(userMod): #Its our user module :)
			if not db.Query( userMod.loginSkel().kindName ).get(): #There's currently no user in the database
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
