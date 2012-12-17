# -*- coding: utf-8 -*-
from server.applications.list import List
from server.skeleton import Skeleton
from server import utils, session
from server.bones import *
from server import errors, conf
#from cone.maintenance import maintenance
from time import time
from google.appengine.ext import ndb
from server.utils import generateExpandoClass
from hashlib import sha512
from google.appengine.api import users
import logging
import datetime

class GoogleUser( List ):
	modulList = None #Cache this list of avaiable modules on this instance
	
	class baseSkel( Skeleton ):
		entityName = "user"
		uid = stringBone( descr="Google's UserID", params={"searchable": True, "frontend_list_visible": True}, required=True, readOnly=True )
		gaeadmin = selectOneBone( descr="Is GAE Admin", values={0:"No", 1:"Yes"}, defaultValue=0, readOnly=True )
		name = stringBone( descr="E-Mail", params={"searchable": True, "frontend_list_visible": True}, required=True )
		access = selectMultiBone( descr="Accessrights", values={}, params={"searchable": True, "frontend_list_visible": True} )
		lastlogin = dateBone( descr="Last Login", readOnly=True )
	
	addSkel = None #You cannot add users directly - they need to sign up with google and log into the application once

	def editSkel( self = None, *args,  **kwargs ):
		skel = GoogleUser.baseSkel()
		accessRights = skel.access.values.copy()
		for right in conf["viur.accessRights"]:
			accessRights[ right ] = _( right )
		skel.access.values = accessRights
		return( skel )
	
	viewSkel = editSkel
	addSuccessTemplate = "user_add_success"

	adminInfo = {	"name": "user", #Name of this modul, as shown in Apex (will be translated at runtime)
			"handler": "base",  #Which handler to invoke
			"icon": "icons/modules/user.png", #Icon for this modul
			"columns":[ "name", "access"] # List of predefined searches as dict {"name": (translated-later),"icon": (path to local icon), "searchobj": (dict of searchparams), columns: (list of bonekeys)}
			}

	def getAuthMethod( self, *args, **kwargs ):
		"""Inform tools like ViUR-Admin which authentication to use"""
		return( "X-GOOGLE-ACCOUNT" )
	getAuthMethod.exposed = True
	
	def getCurrentUser( self, *args, **kwargs ):
		from google.appengine.api import users
		currentUser = users.get_current_user()
		if not currentUser:
			return( None )
		uid = currentUser.user_id()
		mysha512 = sha512()
		mysha512.update( str(uid)+conf["viur.salt"]  )
		uidHash = mysha512.hexdigest()
		user = ndb.Key( utils.generateExpandoClass(self.baseSkel.entityName),  "user-%s" % uidHash ).get()
		if user:
			res = {}
			for k in user._properties.keys():
				res[ k ] = getattr( user, k )
			res[ "id" ] = user.key.urlsafe()
			if not res["access"]:
				res["access"] = []
			return( res )
		else:
			return( None )
		
	def login( self, skey="", *args, **kwargs ):
		def updateCurrentUser():
			currentUser = users.get_current_user()
			uid = currentUser.user_id()
			mysha512 = sha512()
			mysha512.update( str(uid)+conf["viur.salt"]  )
			uidHash = mysha512.hexdigest()
			user = generateExpandoClass( self.baseSkel().entityName ).get_or_insert( "user-%s" % uidHash, uid=uid, name=currentUser.email(), creationdate=datetime.datetime.now(), access=None  )
			#Update the user
			dt = datetime.datetime.now()
			if (not "lastlogin" in user._properties.keys()) or (dt-user.lastlogin)>datetime.timedelta( minutes=30 ):
				#Save DB-Writes: Update the user max once in 30 Minutes
				user.lastlogin = dt
				if users.is_current_user_admin():
					try:
						if not "root" in user.access:
							user.access.append("root")
					except:
						user.access = ["root"]
					user.gaeadmin = 1
				else:
					user.gaeadmin = 0
				user.put()
		if users.get_current_user():
			ndb.transaction( updateCurrentUser )
			return( self.render.loginSucceeded( ) )
		else:
			raise( errors.Redirect( users.create_login_url( self.modulPath+"/login") ) )
	login.exposed = True

	def logout( self,  skey="", *args,  **kwargs ): #fixme
		user = users.get_current_user()
		if not user:
			return( self.render.logoutSuccess( ) )
		if not utils.validateSecurityKey( skey ):
			raise( errors.Forbidden() )
		raise( errors.Redirect( users.create_logout_url( self.modulPath+"/logout" ) ) )
		
	logout.exposed = True

class CustomUser( List ): 
	addTemplate = "user_add"
	addSuccessTemplate = "user_add_success"
	lostPasswordTemplate = "user_lostpassword"
	verifyEmailAddressMail = "user_verify_address"
	passwordRecoveryMail = "user_password_recovery"
	
	def __init__(self, *args, **kwargs ):
		"""Create a new Admin user, if the userDB is empty
		"""
		super( CustomUser, self ).__init__(*args, **kwargs)
		skel = self.loginSkel()
		if not skel._expando.query().get():
			pw = utils.generateRandomString( 13 )
			user = self.addUser( "Admin", pw )
			user.access = ["root"]
			user.status = 10
			user.put()
			logging.warn("Created a new adminuser for you! Username: Admin, Password: %s" % pw)
			utils.sendEMailToAdmins( "Your new ViUR password", "ViUR created a new adminuser for you! Username: Admin, Password: %s" % pw )

	def addUser(self, name, password ):
		skel = self.loginSkel()
		pwHash = sha512( password.encode("utf-8")+conf["viur.salt"] ).hexdigest()
		uidHash = sha512( name.lower().encode("utf-8")+conf["viur.salt"] ).hexdigest()
		return( skel._expando.get_or_insert( uidHash, name=name, name_idx=name.lower(), password=pwHash, creationdate=datetime.datetime.now() ) )

	def getAuthMethod( self, *args, **kwargs ):
		"""Inform tools like Viur-Admin which authentication to use"""
		return( "X-VIUR-INTERNAL" )
	getAuthMethod.exposed = True	
	
	class loginSkel( Skeleton ):
		entityName = "user"
		id = None
		name = emailBone( descr="E-Mail", params={"searchable": True, "frontend_list_visible": True}, required=True )
		password = passwordBone( descr="Passwort", params={"searchable": True, "frontend_list_visible": True,"justinput":True}, required=True )

	class baseSkel( Skeleton ):
		entityName = "user"
		name = emailBone( descr="E-Mail", params={"searchable": True, "frontend_list_visible": True}, required=True )
		access = selectMultiBone( descr="Accessrights", values={"root": "Superuser"}, params={"searchable": True, "frontend_list_visible": True} )
		status = selectOneBone( descr="Account status", values = {
					1: "Waiting for EMail verification",
					2: "Waiting for verification though admin",
					5: "Account disabled",
					10: "Active" }, defaultValue="10")
	
	def addSkel( self ):
		admin=False
		skel = self.baseSkel()
		user = users.get_current_user()  #Check the GAE API
		if users.is_current_user_admin():
			admin=True
		if "user" in dir( conf["viur.mainApp"] ): #Check for our custom user-api
			user = conf["viur.mainApp"].user.getCurrentUser()
			if user and user["access"] and ("%s-add" % self.modulName in user["access"] or "root" in user["access"] ):
				admin=True
		if not admin:
			skel.status = baseBone( defaultValue=10, readOnly=True, visible=False )
			skel.access = baseBone( defaultValue=[], readOnly=True, visible=False )
		else:
			accessRights = skel.access.values.copy()
			for right in conf["viur.accessRights"]:
				accessRights[ right ] = _( right )
			skel.access.values = accessRights
		skel.password = passwordBone( descr="Password", required=True )
		return( skel )

	def editSkel( self, *args,  **kwargs ):
		skel = self.baseSkel()
		accessRights = skel.access.values.copy()
		for right in conf["viur.accessRights"]:
			accessRights[ right ] = _( right )
		skel.access.values = accessRights
		skel.password = passwordBone( descr="Passwort", required=False )
		return( skel )

	class lostPasswordSkel( Skeleton ):
		entityName = "user"
		name = stringBone( descr="Name", required=True )
		password = passwordBone( descr="New Password", required=True )
	
	viewSkel = baseSkel
	
	registrationEnabled = True
	registrationEmailVerificationRequired = True
	registrationAdminVerificationRequired = False
	
	adminInfo = {	"name": "User", #Name of this modul, as shown in Apex (will be translated at runtime)
				"handler": "list",  #Which handler to invoke
				"icon": "icons/modules/user.png", #Icon for this modul
				}
	
	def getCurrentUser( self, *args, **kwargs ):
		return( session.current.get("user") )
	
	def canAdd(self):
		if self.registrationEnabled:
			return( True )
		return( super( CustomUser, self ).canAdd() )

	def add( self, *args, **kwargs ):
		"""
			Override the add-function, as we must ensure that the usernames are unique
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if not self.canAdd( ):
			raise errors.Unauthorized()
		skel = self.addSkel()
		if not skel.fromClient( kwargs ) or len(kwargs)==0 or skey=="" or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.add( skel ) )
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		if skel._expando.query().filter( ndb.GenericProperty( "name_idx" ) == skel.name.value.lower() ).get(): #This username is already taken
			skel.errors["name"] = _("This name is already taken!")
			return( self.render.add( skel ) )
		newUser = self.addUser( skel.name.value, skel.password.value )
		isAdmin = False #He can add & activate a user directly
		user = users.get_current_user()  #Check the GAE API
		if users.is_current_user_admin():
			isAdmin = True
		if "user" in dir( conf["viur.mainApp"] ): #Check for our custom user-api
			user = conf["viur.mainApp"].user.getCurrentUser()
			if user and user["access"] and ("%s-add" % self.modulName in user["access"] or "root" in user["access"] ):
				isAdmin = True
		if not isAdmin:
			if self.registrationEmailVerificationRequired:
				skel.status.value = 1
				skey = utils.createSecurityKey( duration=60*60*24*7 , userid=newUser.key.urlsafe(), name=skel.name.value )
				self.sendVerificationEmail( newUser.key.urlsafe(), skey )
			elif self.registrationAdminVerificationRequired:
				skel.status.value = 2
			else: #No further verification required
				skel.status.value = 10
		id = skel.toDB( newUser.key.urlsafe() )
		self.onItemAdded( id, skel )
		return self.render.addItemSuccess( id, skel )
	add.exposed = True
	add.forceSSL = True

	def login( self, name=None, password=None, skey="", *args, **kwargs ):
		if self.getCurrentUser(): #Were already loggedin
			return( self.render.loginSucceeded( ) )
		if not name or not password or not utils.validateSecurityKey( skey ):
			return( self.render.login( self.loginSkel() ) )
		mysha512 = sha512()
		mysha512.update( password.encode("utf-8")+conf["viur.salt"] )
		dbObj = utils.generateExpandoClass( self.viewSkel.entityName )
		res  = dbObj.query().filter( ndb.GenericProperty("name_idx") == name.lower())\
				.filter( ndb.GenericProperty("password") == mysha512.hexdigest())\
				.filter( ndb.GenericProperty("status") >= 10).get()
		if( not res ):
			return( self.render.login( self.loginSkel(), loginFailed=(skey and name and password) )  )
		else:
			session.current['user'] = {}
			for key in ["name", "status", "access"]:
				try:
					session.current['user'][ key ] = getattr( res, key )
				except: pass
			session.current['user']["id"] = str( res.key.urlsafe() )
			if not "access" in session.current['user'].keys() or not session.current['user']["access"]:
				session.current['user']["access"] = []
			session.current.markChanged()
			return( self.render.loginSucceeded( ) )
	login.exposed = True
	
	def logout( self,  skey="", *args,  **kwargs ): #fixme
		user = session.current.get("user")
		if not user:
			raise errors.Unauthorized()
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		session.current["user"] = None
		return self.render.logoutSuccess( )
	logout.exposed = True

	def edit( self,  *args,  **kwargs ):
		if len( args ) == 0 and not "id" in kwargs and session.current.get("user"):
			kwargs["id"] = session.current['user'].get("user")["id"]
		return( super( CustomUser, self ).edit( *args,  **kwargs ) )
	edit.exposed=True

	def pwrecover( self, authtoken=None, skey=None, *args, **kwargs ):
		if authtoken:
			data = utils.validateSecurityKey( authtoken, True )
			if data and isinstance( data, dict ) and "userid" in data.keys() and "password" in data.keys():
				skel = self.editSkel()
				assert skel.fromDB( data["userid"] )
				skel.password.value = data["password"]
				skel.toDB( data["userid"] )
				return( self.render.passwdRecoverInfo( "success", skel ) )
			else:
				return( self.render.passwdRecoverInfo( "invalid_token", None ) )
		else:
			skel = self.lostPasswordSkel()
			if len(kwargs)==0 or not skel.fromClient( kwargs ):
				return( self.render.passwdRecover( skel, tpl=self.lostPasswordTemplate ) )
			user = self.viewSkel()._expando.query().filter( ndb.GenericProperty("name_idx")==skel.name.value.lower() ).get()
			if not user: #Unknown user
				skel.errors["name"] = _("Unknown user")
				return( self.render.passwdRecover( skel, tpl=self.lostPasswordTemplate ) )
			try:
				if user.changedate>datetime.datetime.now()-datetime.timedelta(days=1): #This user probably has already requested a password reset
					return( self.render.passwdRecoverInfo( "already_send", skel ) ) #within the last 24 hrs
			except AttributeError: #Some newly generated user-objects dont have such a changedate yet
				pass
			user.changedate = datetime.datetime.now()
			user.put()
			key = utils.createSecurityKey( 60*60*24, userid=user.key.urlsafe(), password=skel.password.value )
			self.sendPasswordRecoveryEmail( user.key.urlsafe(), key )
			return( self.render.passwdRecoverInfo( "instructions_send", skel ) )
	pwrecover.exposed = True
	
	def verify(self,  skey,  *args,  **kwargs ):
		data = utils.validateSecurityKey( skey, True )
		skel = self.editSkel()
		if not data or not isinstance( data,  dict ) or not "userid" in data or not skel.fromDB( data["userid"] ):
			return self.render.verifyFailed()
		if self.registrationAdminVerificationRequired:
			skel.status.value = 2
		else:
			skel.status.value = 10
		skel.toDB( data["userid"] )
		return self.render.verifySuccess( data )
	verify.exposed = True
	
	def sendVerificationEmail(self, userID, skey ):
		skel = self.viewSkel()
		assert skel.fromDB( userID )
		skel.skey = baseBone( descr="Skey" )
		skel.skey.value = skey
		utils.sendEMail( [skel.name.value], self.verifyEmailAddressMail, skel )
		
	def sendPasswordRecoveryEmail(self, userID, skey ):
		skel = self.viewSkel()
		assert skel.fromDB( userID )
		skel.skey = baseBone( descr="Skey" )
		skel.skey.value = skey
		utils.sendEMail( [skel.name.value], self.passwordRecoveryMail, skel )


