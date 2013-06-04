# -*- coding: utf-8 -*-
from server.bones import baseBone, numericBone
from server.skeleton import Skeleton
from server import utils
from server import errors, session, conf, securitykey
from server import db
from server import forcePost, forceSSL, exposed, internalExposed
from time import time
from google.appengine.api import users
from datetime import datetime
import logging

class TreeLeafSkel( Skeleton ):
	parentdir = baseBone( descr="Parent", visible=False, indexed=True, readOnly=True )
	parentrepo = baseBone( descr="BaseRepo", visible=False, indexed=True, readOnly=True )

class TreeNodeSkel( TreeLeafSkel ):
	pass
	

class Tree( object ):
	""" 
		This application holds hierarchy data.
		In this application, entries are sorted in directories, which can be nested.
	"""
	adminInfo = {	"name": "TreeApplication", #Name of this modul, as shown in Admin (will be translated at runtime)
			"handler": "tree",  #Which handler to invoke
			"icon": "", #Icon for this modul
			#,"orderby":"changedate",
			#"orderdir":1
			}
	viewLeafSkel = TreeLeafSkel
	viewNodeSkel = TreeNodeSkel

	def __init__( self, modulName, modulPath, *args, **kwargs ):
		self.modulName = modulName
		self.modulPath = modulPath
		if self.adminInfo and self.viewLeafSkel:
			rights = ["add", "edit", "view", "delete"]
			for r in rights:
				rightName = "%s-%s" % (modulName, r )
				if not rightName in conf["viur.accessRights"]:
					conf["viur.accessRights"].append( rightName )

			
	def ensureOwnUserRootNode( self ):
		"""
			Ensures, that an rootNode for the current user exists
			@returns: The Node-object (as ndb.Expando) or None, if this was request was made by a guest
		"""
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if thisuser:
			key = "rep_user_%s" % str( thisuser["id"] )
			return( db.GetOrInsert( key, self.viewLeafSkel().kindName+"_rootNode", creationdate=datetime.now(), rootNode=1, user=str( thisuser["id"] ) ) )

	def ensureOwnModulRootNode( self ):
		"""
			Ensures that the modul-global rootNode exists.
			@returns: The Node-object (as ndb.Expando)
		"""
		key = "rep_modul_repo"
		return( db.GetOrInsert( key, self.viewLeafSkel().kindName+"_rootNode", creationdate=datetime.now(), rootNode=1 ) )


	def getRootNode(self, subRepo):
		"""
			Returns the root-rootNode for a given (sub)-repo
			@param subRepo: RootNode-Key
			@type subRepo: String
			@returns: db.Entity or None
		"""
		repo = db.Get( subRepo )
		if "parentrepo" in repo.keys():
			return( db.Get( repo["parentrepo"] ) )
		elif "rootNode" in repo.keys() and str(repo["rootNode"])=="1":
			return( repo )
		else:
			return( None )


	def isOwnUserRootNode( self, repo ):
		"""
			Checks, if the given rootNode is owned by the current user
			@param repo: Urlsafe-key of the rootNode
			@type repo: String
			@returns: True if the user owns this rootNode, False otherwise
		"""
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if not thisuser:
			return(False)
		repo = self.getRootNode( repo )
		user_repo = self.ensureOwnUserRootNode()
		if str( repo.key() ) == str(user_repo.key()):
			return( True )
		return( False )

	def deleteRecursive( self, nodeKey ):
		"""
			Recursivly processes an delete request
		"""
		skel = self.viewLeafSkel()
		for f in db.Query( self.viewLeafSkel().kindName ).filter( "parentdir", str(nodeKey) ).iter( keysOnly=True ):
			skel.delete( str( f ) )
		skel = self.viewNodeSkel()
		for d in db.Query( self.viewNodeSkel().kindName ).filter( "parentdir", str(repo.key()) ).iter( keysOnly=True ):
			self.deleteDirsRecursive( d )
			skel.delete( d )
		#db.Delete( [x.key() for x in dirs ] )

## External exposed functions

	@exposed
	def listRootNodes(self, name=None ):
		"""
			Renders a list of all available repositories for the current user
		"""
		return( self.render.listRootNodes( self.getAvailableRootNodes( name ) ) )

	
	@exposed
	def list( self, node, skelType, *args, **kwargs ):
		"""
			List the entries and directorys of the given rootNode under the given path
			@param rootNode: Urlsafe-key of the rootNode
			@type rootNode: String
			@param path: Path to the level which should be displayed
			@type path: String
		"""
		if skelType == "node":
			skel = self.viewNodeSkel()
		elif skelType == "leaf":
			skel = self.viewLeafSkel()
		else:
			raise errors.NotAcceptable()
		if not self.canList( node, skelType ):
			raise errors.Unauthorized()
		query = skel.all()
		if "search" in kwargs.keys() and kwargs["search"]:
			query.filter( "parentrepo =", str(node) )
		else:
			query.filter( "parentdir =", str(node) )
		query.mergeExternalFilter( kwargs )
		res = query.fetch( )
		return( self.render.list( res, ) )
	
	
	@exposed
	def view( self, id, skelType, *args, **kwargs ):
		"""
			Prepares and renders a single entry for viewing
		"""
		if skelType == "node":
			skel = self.viewNodeSkel()
		elif skelType == "leaf":
			skel = self.viewLeafSkel()
		else:
			raise errors.NotAcceptable()
		if not self.canView( id, skelType ):
			raise errors.Unauthorized()
		if not skel.fromDB( id ):
			raise errors.NotFound()
		self.onItemViewed( skel, skelType )
		return( self.render.view( skel ) )

	
	@exposed
	@forceSSL
	def add( self, node, skelType, skey="", *args, **kwargs ):
		assert skelType in ["node","leaf"]
		if skelType == "node":
			skel = self.viewNodeSkel()
		elif skelType == "leaf":
			skel = self.viewLeafSkel()
		else:
			raise errors.NotAcceptable()
		parentNodeSkel = self.editNodeSkel()
		if not parentNodeSkel.fromDB( node ):
			raise errors.NotFound()
		if not self.canAdd( node, skelType ):
			raise errors.Unauthorized()
		if len(kwargs)==0 or skey=="" or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.add( skel ) )
		skel.parentdir.value = str( node )
		skel.parentrepo.value = parentNodeSkel.parentrepo.value or str( node )
		id = skel.toDB( )
		self.onItemAdded( skel, skelType )
		return self.render.addItemSuccess( skel )

	@exposed
	@forceSSL
	def edit( self, id, skelType, skey="", *args, **kwargs ):
		"""
			Edit the entry with the given id
		"""
		if skelType == "node":
			skel = self.viewNodeSkel()
		elif skelType == "leaf":
			skel = self.viewLeafSkel()
		else:
			raise( errors.NotAcceptable() )
		if not skel.fromDB( id ):
			raise errors.NotFound()
		if not self.canEdit( skel ):
			raise errors.Unauthorized()
		if len(kwargs)==0 or skey=="" or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.edit( skel ) )
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		skel.toDB( id )
		self.onItemEdited( skel, skelType )
		return self.render.editItemSuccess( skel )

	@exposed
	@forceSSL
	@forcePost
	def delete( self, id, skelType ):
		"""
			Deletes an entry or an directory (including its contents)
			@param rootNode: Urlsafe-key of the rootNode
			@type rootNode: String
			@param path: Path in which entries/dirs should be deleted
			@type path: String
			@param name: Name of the entry/dir which should be deleted
			@type name: String
			@param type: "entry" if an entry should be deleted, otherwise try to delte a directory with this name
			@type type: String
		"""		
		if skelType == "node":
			skel = self.viewNodeSkel()
		elif skelType == "leaf":
			skel = self.viewLeafSkel()
		else:
			raise( errors.NotAcceptable() )
		if not self.canDelete( id, skelType ):
			raise errors.Unauthorized()
		if not skel.fromDB( id ):
			raise errors.NotFound()
		if type=="leaf":
			skel.delete( id )
		else:
			self.deleteRecursive( id )
			skel.delete( id )
		self.onItemDeleted( skel, skelType )
		return( self.render.deleteSuccess( skel, skelType=skelType ) )

	@exposed
	@forceSSL
	@forcePost
	def move( self, id, skelType, destNode ):
		"""
			Move an node or a leaf to another node  (including its contents).
			@param srcrepo: RootNode-key from which has been copied/moved
			@type srcrepo: String
			@param srcpath: Path from which the entry has been copied/moved
			@type srcpath: String
			@type name: Name of the entry which has been copied/moved
			@type name: String
			@param destrepo: RootNode-key to which has been copied/moved
			@type destrepo: String
			@param destpath: Path to which the entries has been copied/moved
			@type destpath: String
			@param type: "entry": Copy/Move an entry, everything else: Copy/Move an directory
			@type type: string
			@param deleteold: "0": Copy, "1": Move
			@type deleteold: string
		"""
		if skelType == "node":
			srcSkel = self.viewNodeSkel()
		elif skelType == "leaf":
			srcSkel = self.viewLeafSkel()
		else:
			raise( errors.NotAcceptable() )
		destSkel = self.editNodeSkel()
		if not self.canMove( id, skelType, destNode ):
			raise errors.Unauthorized()
		if id==destNode: 
			# Cannot move a node into itself
			raise errors.NotAcceptable()
		if not srcSkel.fromDB( id ) or not destSkel.fromDB( destNode ):
			# Could not find one of the entities
			raise errors.NotFound()
		srcSkel.parentdir.value = str( destNode )
		srcSkel.parentrepo.value = destSkel.parentrepo.value #Fixme: Need to rekursive fixing to parentrepo?
		srcSkel.toDB( id )
		return( self.render.editItemSuccess( srcSkel, skelType=skelType, action="move", destNode = destSkel ) )

## Default accesscontrol functions 

	def canList( self, node, skelType ):
		"""
			Checks if the current user has the right to list a node
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user and user["access"] and "%s-view" % self.modulName in user["access"]:
			return( True )
		return( False )
		
	def canView( self, node, skelType ):
		"""
			Checks if the current user has the right to view an entry
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user and user["access"] and "%s-view" % self.modulName in user["access"]:
			return( True )
		return( False )
		
	def canAdd( self, node, skelType ):
		"""
			Checks if the current user has the right to add a new entry
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user and user["access"] and "%s-add" % self.modulName in user["access"]:
			return( True )
		return( False )
		
	def canEdit( self, node, skelType ):
		"""
			Checks if the current user has the right to edit an entry
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user and user["access"] and "%s-edit" % self.modulName in user["access"]:
			return( True )
		return( False )
		
	def canDelete( self, node, skelType ):
		"""
			Checks if the current user has the right to delete an entry
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user and user["access"] and "%s-delete" % self.modulName in user["access"]:
			return( True )
		return( False )

	def canMove( self, node, skelType, destNode ):
		"""
			Checks if the current user has the right to add move an entry
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user and user["access"] and "%s-move" % self.modulName in user["access"]:
			return( True )
		return( False )

## Overridable eventhooks

	def onItemAdded( self, skel, skelType ):
		"""
			Hook. Can be overriden to hook the onItemAdded-Event
			@param skel: Skeleton with the data which has been added
			@type skel: Skeleton
		"""
		logging.info("Entry added: %s" % skel.id.value )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
	
	def onItemEdited( self, skel, skelType ):
		"""
			Hook. Can be overriden to hook the onItemEdited-Event
			@param skel: Skeleton with the data which has been edited
			@type skel: Skeleton
		"""
		logging.info("Entry changed: %s" % skel.id.value )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
		
	def onItemViewed( self, skel, skelType ):
		"""
			Hook. Can be overriden to hook the onItemViewed-Event
			@param skel: Skeleton with the data which has been viewed
			@type skel: Skeleton
		"""
		pass
	

	def onItemDeleted( self, skel, skelType ): #Fixme: Fix Docstring
		"""
			Hook. Can be overriden to hook the onItemDeleted-Event
			Note: Saving the skeleton again will undo the deletion
			(if the skeleton was a leaf or a node with no childen).
		"""
		logging.info("Entry deleted: %s (%s)" % ( skel.id.value, skelType ) )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )

Tree.admin = True
Tree.jinja2 = True
Tree.ops = True
