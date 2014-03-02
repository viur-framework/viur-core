# -*- coding: utf-8 -*-
from server.applications.list import List
from server.skeleton import Skeleton
from server import utils, session
from server.bones import *
from server.bones.passwordBone import pbkdf2
from server import errors, conf, securitykey
from server import db
from hashlib import sha512
from google.appengine.api import users, app_identity
import logging
import datetime

class userSkel( Skeleton ):
	kindName = "user"
	uid = stringBone( descr="Google's UserID", indexed=True, required=True, readOnly=True )
	gaeadmin = selectOneBone( descr="Is GAE Admin", values={0:"No", 1:"Yes"}, defaultValue=0, readOnly=True )
	name = stringBone( descr="E-Mail", indexed=True,required=True,searchable=True )
	access = selectMultiBone( descr="Accessrights", values={}, indexed= True )
	lastlogin = dateBone( descr="Last Login", readOnly=True )


class GoogleUser( List ):
	modulList = None #Cache this list of avaiable modules on this instance

	addSkel = None #You cannot add users directly - they need to sign up with google and log into the application once

	def editSkel( self, *args,  **kwargs ):
		skel = super( GoogleUser, self ).editSkel()
		accessRights = skel["access"].values.copy()
		for right in conf["viur.accessRights"]:
			accessRights[ right ] = _( right )
		skel["access"].values = accessRights
		return( skel )

	viewSkel = editSkel
	addSuccessTemplate = "user_add_success"

	adminInfo = {	"name": "user", #Name of this modul, as shown in ViUR Admin (will be translated at runtime)
			"handler": "list",  #Which handler to invoke
			"icon": "icons/modules/users.svg", #Icon for this modul
			"columns":[ "name", "access"] # List of default-visible columns
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
		try:
			user = db.Get( db.Key.from_path( self.viewSkel().kindName,  "user-%s" % uidHash ) )
		except db.EntityNotFoundError:
			#This user is known to the appengine, but not to us yet (he didnt use /user/login)
			return( None )
		if user:
			res = {}
			for k in user.keys():
				res[ k ] = user[ k ]
			res[ "id" ] = str( user.key() )
			if not res["access"]:
				res["access"] = []
			return( res )
		else:
			return( None )

	def onLogin(self):
		pass

	def login( self, skey="", *args, **kwargs ):
		def updateCurrentUser():
			currentUser = users.get_current_user()
			uid = currentUser.user_id()
			mysha512 = sha512()
			mysha512.update( str(uid)+conf["viur.salt"]  )
			uidHash = mysha512.hexdigest()

			user = db.GetOrInsert( "user-%s" % uidHash, kindName=self.viewSkel().kindName, uid=uid, name=currentUser.email(), creationdate=datetime.datetime.now(), access=None )
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
		if users.get_current_user():
			session.current.reset()
			db.RunInTransaction( updateCurrentUser )
			self.onLogin()
			return( self.render.loginSucceeded( ) )
		else:
			raise( errors.Redirect( users.create_login_url( self.modulPath+"/login") ) )
	login.exposed = True
	login.forceSSL = True

	def logout( self,  skey="", *args,  **kwargs ): #fixme
		user = users.get_current_user()
		if not user:
			return( self.render.logoutSuccess( ) )
		if not securitykey.validate( skey ):
			raise( errors.Forbidden() )
		raise( errors.Redirect( users.create_logout_url( self.modulPath+"/logout" ) ) )
	logout.exposed = True
	logout.forceSSL = True

	def view(self, id, *args, **kwargs):
		"""
			Allow a special id "self" to reference always the current user
		"""
		if id=="self":
			user = self.getCurrentUser()
			if user:
				return( super( GoogleUser, self ).view( user["id"], *args, **kwargs ) )
		return( super( GoogleUser, self ).view( id, *args, **kwargs ) )
	view.exposed=True