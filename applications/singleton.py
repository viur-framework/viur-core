# -*- coding: utf-8 -*-
from server.bones import baseBone
from server.skeleton import Skeleton, skeletonByKind
from server import utils, session,  errors, conf, securitykey
from google.appengine.api import users
from google.appengine.ext import db
import logging

class Singleton( object ):
	"""
		Provides an application, which operates on excatly one Skeleton.
		The default-implementation uses one, global Skeleton (eg. usefull for side-wide configuration).
		However, it can be easily adapted to provide one Skeleton per user.
	"""
	
	adminInfo = {	"name": "BaseApplication", #Name of this modul, as shown in ViUR Admin (will be translated at runtime)
				"handler": "singleton",  #Which handler to invoke
				"icon": "", #Icon for this modul
				}
				
	def getKey(self):
		"""
			Returns the DB-Key for the current context.
			This implementation provides one modul-global Key.
			This function *must* return *excatly one* key at any given time in any given context.
			
			@returns String
		"""
		return( "%s-modulkey" % self.editSkel().kindName )

	def __init__( self, modulName, modulPath, *args, **kwargs ):
		self.modulName = modulName
		self.modulPath = modulPath
		if self.adminInfo:
			rights = ["edit", "view"]
			for r in rights:
				rightName = "%s-%s" % ( modulName, r )
				if not rightName in conf["viur.accessRights"]:
					conf["viur.accessRights"].append( rightName )

	def viewSkel( self, *args, **kwargs ):
		return( skeletonByKind( unicode( type(self).__name__).lower() )() )

	def editSkel( self, *args, **kwargs ):
		return( skeletonByKind( unicode( type(self).__name__).lower() )() )

	def preview( self, skey, *args, **kwargs ):
		"""
			Renders the viewTemplate with the values given.
			This allows to preview an entry without having to save it first
		"""
		if not self.canPreview( ):
			raise errors.Unauthorized()
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		skel = self.viewSkel()
		skel.fromClient( kwargs )
		return( self.render.view( skel ) )
	preview.exposed = True
	
	def view( self, *args, **kwargs ):
		"""
			Prepares and renders the entry for viewing
		"""
		skel = self.viewSkel()
		if not self.canView( ):
			raise errors.Unauthorized()
		id = str( db.Key.from_path( self.editSkel().kindName, self.getKey() ) )
		if not skel.fromDB( id ):
			raise errors.NotFound()
		self.onItemViewed( skel )
		return( self.render.view( skel ) )
	view.exposed = True

	def edit( self, *args, **kwargs ):
		"""
			Edit this entry
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		skel = self.editSkel()
		if not self.canEdit( ):
			raise errors.Unauthorized()
		id = str( db.Key.from_path( self.editSkel().kindName, self.getKey() ) )
		skel.fromDB( id )
		if len(kwargs)==0 or skey=="" or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.edit( skel ) )
		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()
		skel.toDB( )
		self.onItemEdited( skel )
		return self.render.editItemSuccess( skel )
	edit.exposed = True
	edit.forceSSL = True


	def getContents( self ):
		"""
			Returns the data of this singleton application as viewSkel.
		"""
		skel = self.viewSkel()
		id = str( db.Key.from_path( self.viewSkel().kindName, self.getKey() ) )
		if not skel.fromDB( id ):
			return( None )
		return( skel )

	def canPreview( self ):
		"""
			Checks if the current user has the right to use the preview function
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user["access"] and "%s-edit" % self.viewSkel.kindName in user["access"]:
			return( True )
		return( False )

	def canEdit( self ):
		"""
			Checks if the current user has the right to edit this entry
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user["access"] and "%s-edit" % self.modulName in user["access"]:
			return( True )
		return( False )

	def canView(self):
		"""
			Checks if the current user has the right to view this entry
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user["access"] and "%s-view" % self.modulName in user["access"]:
			return( True )
		return( False )

	def onItemEdited( self, skel ):
		"""
			Hook. Can be overriden to hook the onItemEdited-Event
			@param skel: Skeleton with the data which has been edited
			@type skel: Skeleton
		"""
		logging.info("Entry changed: %s" % id )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
		
	def onItemViewed( self, skel ):
		"""
			Hook. Can be overriden to hook the onItemViewed-Event
			@param skel: Skeleton with the data which has been viewed
			@type skel: Skeleton
		"""
		pass
	
	
Singleton.admin=True
Singleton.jinja2=True
Singleton.vi=True
