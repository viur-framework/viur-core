# -*- coding: utf-8 -*-
from server.bones import baseBone, numericBone
from server.skeleton import Skeleton
from server import utils
from server import errors, session, conf, securitykey
from server import db
from server import forcePost, forceSSL, exposed, internalExposed
from time import time
from server.tasks import callDeferred
from google.appengine.api import users
from datetime import datetime
import logging

class TreeLeafSkel( Skeleton ):
	parentdir = baseBone( descr="Parent", visible=False, indexed=True, readOnly=True )
	parentrepo = baseBone( descr="BaseRepo", visible=False, indexed=True, readOnly=True )
	
	def fromDB( self, *args, **kwargs ):
		res = super( TreeLeafSkel, self ).fromDB( *args, **kwargs )
		# Heal missing parent-repo values
		if res and not self["parentrepo"].value:
			dbObj = db.Get( self["id"].value )
			if not "parentdir" in dbObj.keys(): #RootNode
				return( res )
			while( "parentdir" in dbObj.keys() and dbObj["parentdir"] ):
				dbObj = db.Get( dbObj[ "parentdir" ] )
			self["parentrepo"].value = str( dbObj.key() )
			self.toDB(  )
		return( res )

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


	def jinjaEnv(self, env ):
		"""
			Provide some additional Functions to the template
		"""
		env.globals["getPathToKey"] = self.pathToKey
		return( env )

	@callDeferred
	def deleteRecursive( self, nodeKey ):
		"""
			Recursivly processes an delete request
		"""
		for f in db.Query( self.viewLeafSkel().kindName ).filter( "parentdir", str(nodeKey) ).iter( keysOnly=True ):
			s = self.viewLeafSkel()
			if not s.fromDB( f ):
				continue
			s.delete()
		for d in db.Query( self.viewNodeSkel().kindName ).filter( "parentdir", str(nodeKey) ).iter( keysOnly=True ):
			self.deleteRecursive( str(d) )
			s = self.viewNodeSkel()
			if not s.fromDB( d ):
				continue
			s.delete()

		#db.Delete( [x.key() for x in dirs ] )
	
	@callDeferred
	def updateParentRepo( self, parentNode, newRepoKey, depth=0 ):
		"""
			Recursivly fixes the parentrepo key after a move operation
			@param parentNode: Key of the node wich children should be fixed
			@type parentNode: String
			@param newNode: Key of the new repository
			@type newNode: String
			@param depth: Safety precation preventing infinitive loops
			@type depth: Int
		"""
		if depth>99:
			logging.critical("Maximum recursion depth reached in server.applications.tree/fixParentRepo")
			logging.critical("Your data is corrupt!")
			logging.critical("Params: parentNode: %s, newRepoKey: %s" % (parentNode, newRepoKey ) )
			return
		def fixTxn( nodeKey, newRepoKey ):
			node = db.Get( nodeKey )
			node["parentrepo"] = newRepoKey
			db.Put( node )
		# Fix all nodes
		for repo in db.Query( self.viewNodeSkel().kindName ).filter( "parentdir =", parentNode ).iter( keysOnly=True ):
			self.updateParentRepo( str( repo ), newRepoKey, depth=depth+1 )
			db.RunInTransaction( fixTxn, str( repo ), newRepoKey )
		# Fix the leafs on this level
		for repo in db.Query( self.viewLeafSkel().kindName ).filter( "parentdir =", parentNode ).iter( keysOnly=True ):
			db.RunInTransaction( fixTxn, str( repo ), newRepoKey )



## Internal exposed functions

	@internalExposed
	def pathToKey( self, key ):
		"""
			Returns the recursively expaned Path through the Hierarchy from the RootNode to the given Node
			@param key: URlsafe Key of the destination node
			@type key: String:
			@returns: An nested dictionary with Informations about all nodes in the path from Root to the given Node
		"""
		nodeSkel = self.viewNodeSkel()
		if not nodeSkel.fromDB( key ):
			raise errors.NotFound()
		if not self.canList( "node", key ):
			raise errors.Unauthorized()
		res = [ self.render.collectSkelData( nodeSkel ) ]
		for x in range(0,99):
			if not nodeSkel["parentdir"].value:
				break
			parentdir = nodeSkel["parentdir"].value
			nodeSkel = self.viewNodeSkel()
			if not nodeSkel.fromDB( parentdir ):
				break
			res.append( self.render.collectSkelData( nodeSkel ) )
		return( res[ : : -1 ] )


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

## External exposed functions

	@exposed
	def listRootNodes(self, name=None, *args, **kwargs ):
		"""
			Renders a list of all available repositories for the current user
		"""
		return( self.render.listRootNodes( self.getAvailableRootNodes( name ) ) )


	@exposed
	def list( self, skelType, node, *args, **kwargs ):
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
		if not self.canList( skelType, node ):
			raise errors.Unauthorized()
		nodeSkel = self.viewNodeSkel()
		if not nodeSkel.fromDB( node ):
			raise errors.NotFound()
		query = skel.all()
		if "search" in kwargs.keys() and kwargs["search"]:
			query.filter( "parentrepo =", str(nodeSkel["id"].value) )
		else:
			query.filter( "parentdir =", str(nodeSkel["id"].value) )
		query.mergeExternalFilter( kwargs )
		res = query.fetch( )
		return( self.render.list( res, node=str(nodeSkel["id"].value) ) )
	
	
	@exposed
	def view( self, skelType, id, *args, **kwargs ):
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
		self.onItemViewed( skel )
		return( self.render.view( skel ) )

	
	@exposed
	@forceSSL
	def add( self, skelType, node, *args, **kwargs ):
		assert skelType in ["node","leaf"]
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if skelType == "node":
			skel = self.viewNodeSkel()
		elif skelType == "leaf":
			skel = self.viewLeafSkel()
		else:
			raise errors.NotAcceptable()
		parentNodeSkel = self.editNodeSkel()
		if not parentNodeSkel.fromDB( node ):
			raise errors.NotFound()
		if not self.canAdd( skelType, node ):
			raise errors.Unauthorized()
		if len(kwargs)==0 or skey=="" or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.add( skel ) )
		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()
		skel["parentdir"].value = str( node )
		skel["parentrepo"].value = parentNodeSkel["parentrepo"].value or str( node )
		id = skel.toDB( )
		self.onItemAdded( skel )
		return self.render.addItemSuccess( skel )

	@exposed
	@forceSSL
	def edit( self, skelType, id, skey="", *args, **kwargs ):
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
		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()
		skel.toDB( )
		self.onItemEdited( skel )
		return self.render.editItemSuccess( skel )

	@exposed
	@forceSSL
	@forcePost
	def delete( self, skelType, id, *args, **kwargs ):
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
			raise errors.NotAcceptable()

		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""

		if not skel.fromDB( id ):
			raise errors.NotFound()

		if not self.canDelete( skel, skelType ):
			raise errors.Unauthorized()

		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		if skelType == "leaf":
			skel.delete()
		else:
			self.deleteRecursive( id )
			skel.delete()

		self.onItemDeleted( skel )
		return self.render.deleteSuccess( skel, skelType=skelType )

	@exposed
	@forceSSL
	@forcePost
	def move( self, skelType, id, destNode, *args, **kwargs ):
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
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		destSkel = self.editNodeSkel()
		if not self.canMove( id, skelType, destNode ):
			raise errors.Unauthorized()
		if id==destNode: 
			# Cannot move a node into itself
			raise errors.NotAcceptable()
		## Test for recursion
		isValid = False
		currLevel = db.Get( destNode )
		for x in range(0,99):
			if str(currLevel.key())==id:
				break
			if "rootNode" in currLevel.keys() and currLevel["rootNode"]==1:
				#We reached a rootNode
				isValid=True
				break
			currLevel = db.Get( currLevel["parentdir"] )
		if not isValid:
			raise errors.NotAcceptable()
		#Test if id points to a rootNone
		tmp = db.Get( id )
		if "rootNode" in tmp.keys() and tmp["rootNode"]==1:
			#Cant move a rootNode away..
			raise errors.NotAcceptable()
		if not srcSkel.fromDB( id ) or not destSkel.fromDB( destNode ):
			# Could not find one of the entities
			raise errors.NotFound()
		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()
		srcSkel["parentdir"].value = str( destNode )
		srcSkel["parentrepo"].value = destSkel["parentrepo"].value #Fixme: Need to recursive fixing to parentrepo?
		srcSkel.toDB( )
		self.updateParentRepo( id, destSkel["parentrepo"].value )
		return( self.render.editItemSuccess( srcSkel, skelType=skelType, action="move", destNode = destSkel ) )

## Default accesscontrol functions 

	def canList( self, skelType, node ):
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
		
	def canView( self, skelType, node ):
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
		
	def canAdd( self, skelType, node ):
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
		
	def canEdit( self, skelType, node=None ):
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
		
	def canDelete( self, skelType, node ):
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

	def canMove( self, skelType, node, destNode ):
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

	def onItemAdded( self, skel ):
		"""
			Hook. Can be overriden to hook the onItemAdded-Event
			@param skel: Skeleton with the data which has been added
			@type skel: Skeleton
		"""
		logging.info("Entry added: %s" % skel["id"].value )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
	
	def onItemEdited( self, skel ):
		"""
			Hook. Can be overriden to hook the onItemEdited-Event
			@param skel: Skeleton with the data which has been edited
			@type skel: Skeleton
		"""
		logging.info("Entry changed: %s" % skel["id"].value )
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
	

	def onItemDeleted( self, skel ): #Fixme: Fix Docstring
		"""
			Hook. Can be overriden to hook the onItemDeleted-Event
			Note: Saving the skeleton again will undo the deletion
			(if the skeleton was a leaf or a node with no childen).
		"""
		logging.info("Entry deleted: %s (%s)" % ( skel["id"].value, type(skel) ) )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )

Tree.admin = True
Tree.jinja2 = True
Tree.vi = True
