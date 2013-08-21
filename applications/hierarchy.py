# -*- coding: utf-8 -*-
from server.bones import baseBone, numericBone
from server.skeleton import Skeleton, skeletonByKind
from server import utils, errors, session, conf, request, securitykey
from server import db
from server import forcePost, forceSSL, exposed, internalExposed
from time import time
from google.appengine.api import users
from datetime import datetime
import logging

class HierarchySkel( Skeleton ):
	parententry = baseBone( descr="Parent", visible=False, indexed=True, readOnly=True )
	parentrepo = baseBone( descr="BaseRepo", visible=False, indexed=True, readOnly=True )
	sortindex = numericBone( descr="SortIndex", mode="float", visible=False, indexed=True, readOnly=True )
	
	def preProcessSerializedData( self, dbfields ):
		if not ("sortindex" in dbfields.keys() and dbfields["sortindex"] ):
			dbfields[ "sortindex" ] = time()
		return( dbfields )


class Hierarchy( object ):
	""" 
		This application holds hierarchy data.
		In this application, entries are direct children of each other.
	"""
	
	
	adminInfo = {	"name": "BaseApplication", #Name of this modul, as shown in Admin (will be translated at runtime)
			"handler": "hierarchy",  #Which handler to invoke
			"icon": "", #Icon for this modul
			#,"orderby":"changedate",
			#"orderdir":1
			}

	def viewSkel( self, *args, **kwargs ):
		return( skeletonByKind( unicode( type(self).__name__).lower() )() )
	
	def addSkel( self, *args, **kwargs ):
		return( skeletonByKind( unicode( type(self).__name__).lower() )() )

	def editSkel( self, *args, **kwargs ):
		return( skeletonByKind( unicode( type(self).__name__).lower() )() )

	def __init__( self, modulName, modulPath, *args, **kwargs ):
		self.modulName = modulName
		self.modulPath = modulPath
		if self.adminInfo: # and self.editSkel
			rights = ["add", "edit", "view", "delete"]
			for r in rights:
				rightName = "%s-%s" % ( modulName, r )
				if not rightName in conf["viur.accessRights"]:
					conf["viur.accessRights"].append( rightName )

	def jinjaEnv(self, env ):
		"""
			Provide some additional Functions to the template
		"""
		env.globals["getPathToKey"] = self.pathToKey
		env.globals["canAdd"] = self.canAdd
		env.globals["canPreview"] = self.canPreview
		env.globals["canEdit"] = self.canEdit
		env.globals["canView"] = self.canView
		env.globals["canDelete"] = self.canDelete
		env.globals["canSetIndex"] = self.canSetIndex
		env.globals["canList"] = self.canList
		env.globals["canReparent"] = self.canReparent
		return( env )


	def getRootNode(self, entryKey ):
		"""
			Returns the root for a given child.
			
			@parm entryKey: URL-Safe Key of thechild entry
			@type entryKey: string
			@returns: Entity
		"""
		repo = db.Get( entryKey )
		while repo and  "parententry" in repo.keys():
			repo = db.Get( repo["parententry"] )
		assert repo and repo.key().kind() == self.viewSkel().kindName+"_rootNode"
		return( repo )

	def isValidParent(self, parent ):
		"""
		Checks wherever a given parent is valid.
		
		@param parent: Parent to test
		@type parent: String
		@returns: bool
		"""
		if self.viewSkel().fromDB( parent ): #Its a normal node
			return( True )
		try:
			assert self.getRootNode( parent )
			return( True ) #Its a rootNode :)
		except:
			pass
		return( False )


	def ensureOwnUserRootNode( self ):
		"""
			Ensures, that an rootNode for the current user exists.
			
			@returns: The Node-object (as ndb.Expando) or None, if this was request was made by a guest
		"""
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if thisuser:
			key = "rep_user_%s" % str( thisuser["id"] )
			kindName = self.viewSkel().kindName+"_rootNode"
			return( db.GetOrInsert( key, kindName=kindName, creationdate=datetime.now(), rootNode=1, user=str( thisuser["id"] ) ) )


	def ensureOwnModulRootNode( self ):
		"""
			Ensures that the modul-global rootNode exists.
			
			@returns: The Node-object (as ndb.Expando)
		"""
		key = "rep_modul_repo"
		kindName = self.viewSkel().kindName+"_rootNode"
		return( db.GetOrInsert( key, kindName=kindName, creationdate=datetime.now(), rootNode=1 ) )


	def isOwnUserRootNode( self, repo ):
		"""
			Checks, if the given rootNode is owned by the current user
			
			@param repo: Urlsafe-key of the rootNode
			@type repo: String
			@returns: True if the user owns this rootNode, False otherwise
		"""
		thisuser = user.get_current_user()
		if not thisuser:
			return(False)
		repo = self.getRootNode( repo )
		user_repo = self.ensureOwnUserRootNode()
		if str( repo.key.urlsafe() ) == user_repo.key.urlsafe():
			return( True )
		return( False )


	def deleteRecursive( self, key ):
		"""
			Recursivly processes an delete request
		"""
		vs = self.editSkel()
		entrys = db.Query( self.viewSkel().kindName ).filter( "parententry", str(key) ).run()
		for e in entrys:
			self.deleteRecursive( str( e.key() ) )
			vs.delete( str( e.key() ) )
		vs.delete( key )

## Internal exposed functions

	@internalExposed
	def pathToKey( self, key=None ):
		"""
			Returns the recursively expaned Path through the Hierarchy from the RootNode to the given Node
			@param key: URlsafe Key of the destination node
			@type key: String:
			@returns: An nested dictionary with Informations about all nodes in the path from Root to the given Node
		"""
		def getName( obj ):
			"""
				Tries to return a suitable name for the given object
			"""
			if "name " in obj.keys():
				return( obj["name"] )
			skel = self.viewSkel()
			if "name" in dir( skel ):
				nameBone = skel.name
				if isinstance( nameBone, baseBone ) and "languages" in dir( nameBone ) and nameBone.languages:
					skel.setValues( obj )
					return( unicode( skel.name.value ) )
			return( None )
			
		availableRepos = self.getAvailableRootNodes()
		if not key:
			try:
				key = availableRepos[0]["key"]
			except:
				raise errors.NotFound()
			keylist = [ ]
		else:
			if str(key).isdigit():
				key = str( db.Key.from_path( self.viewSkel().kindName, int(key) ) )
			keylist = [ key ]
		if not self.canList( key ):
			raise errors.Unauthorized()
		res = []
		lastChildren = []
		for x in range(0,99):
			q = db.Query( self.viewSkel().kindName )
			q.filter( "parententry =", str(key) )
			q.order( "sortindex" )
			entryObjs = q.run( 100 )
			lastChildren = res[ : ]
			res = []
			for obj in entryObjs:
				if "parententry" in obj.keys():
					parent = str( obj["parententry"] ) 
				else:
					parent = None
				r = {	"name": getName( obj ),
					"id": str(obj.key()), 
					"parent": parent,
					"hrk": obj["hrk"] if "hrk" in obj.keys() else None,
					"active":(str(obj.key()) in keylist )}
				if r["active"]:
					r["children"] = lastChildren
				res.append( r )
			if key in [ x["key"] for x in availableRepos]:
				break
			else:
				item = db.Get( str( key ) )
				if item and "parententry" in item.keys():
					keylist.append( key )
					key = item["parententry"]
				else:
					break
		return( res )

## External exposed functions

	@exposed
	def listRootNodes(self, *args, **kwargs ):
		"""
			Renders a list of all available repositories for the current user
		"""
		return( self.render.listRootNodes( self.getAvailableRootNodes( *args, **kwargs ) ) )
		

	@exposed
	def preview( self, skey, *args, **kwargs ):
		"""
			Renders the viewTemplate with the values given.
			This allows to preview an entry without having to save it first
		"""
		if not self.canPreview( ):
			raise errors.Unauthorized()
		if not securitykey.verify( skey ):
			raise errors.PreconditionFailed()
		skel = self.viewSkel()
		skel.fromClient( kwargs )
		return( self.render.view( skel ) )


	@forceSSL
	@forcePost
	@exposed
	def reparent( self, item, dest, skey, *args, **kwargs ):
		"""
			Moves an entry (and everything beneath) to another parent-node.
			
			@param item: Urlsafe-key of the item which will be moved
			@type item: String
			@param dest: Urlsafe-key of the new parent for this item
			@type dest: String
		"""
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		if not self.canReparent( item, dest ):
			raise errors.Unauthorized()
		if not self.isValidParent( dest ):
			raise errors.NotAcceptable()
		fromItem = db.Get( item )
		fromItem["parententry"] = dest 
		fromItem["parentrepo"] = str( self.getRootNode( dest ).key() )
		db.Put( fromItem )
		return( self.render.reparentSuccess( obj=fromItem ) )

	
	@forceSSL
	@forcePost
	@exposed
	def setIndex( self, item, index, skey, *args, **kwargs ):
		"""
			Changes the order of the elements in the current level by changing the index of this item.
			@param item: Urlsafe-key of the item which index should be changed
			@type item: String
			@param index: New index for this item. Must be castable to float
			@type index: String
		"""
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		if not self.canSetIndex( item, index ):
			raise errors.Unauthorized()
		fromItem = db.Get( item )
		fromItem["sortindex"] = float( index )
		db.Put( fromItem )
		return( self.render.setIndexSuccess( obj=fromItem ) )


	@forceSSL
	@forcePost
	@exposed
	def delete( self, id, skey ):
		"""
			Delete an entry.
		"""
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		skel = self.editSkel()
		if not skel.fromDB( id ):
			raise errors.NotFound()
		if not self.canDelete( id ):
			raise errors.Unauthorized()
		self.deleteRecursive( id )
		self.onItemDeleted( skel )
		return( self.render.deleteSuccess( id ) )


	@exposed
	def view( self, *args, **kwargs ):
		"""
			Prepares and renders a single entry for viewing
		"""
		if "id" in kwargs:
			id = kwargs["id"]
		elif( len( args ) >= 1 ):
			id= args[0]
		else:
			raise errors.NotAcceptable()
		skel = self.viewSkel()
		if not self.canView( id ):
			raise errors.Unauthorized()
		if not skel.fromDB( id ):
			raise errors.NotFound()
		self.onItemViewed( id, skel )
		return( self.render.view( skel ) )


	@exposed
	def list( self, parent, *args, **kwargs ):
		"""
			List the entries which are direct childs of the given parent
			@param parent: Urlsafe-key of the parent
			@type parent: String
		"""
		if not parent or not self.canList( parent ):
			raise errors.Unauthorized()
		parentSkel = self.viewSkel()
		if not parentSkel.fromDB( parent ):
			if not str(parent) in [str(x["key"]) for x in self.getAvailableRootNodes()]:
				#It isn't a rootNode either
				raise errors.NotFound()
			else:
				parentSkel = None
		query = self.viewSkel().all()
		query.mergeExternalFilter( kwargs )
		query.filter( "parententry", parent )
		return( self.render.list( query.fetch(), parent=parent, parentSkel=parentSkel ) )


	@forceSSL
	@exposed
	def edit( self, *args, **kwargs ):
		"""
			Edit the entry with the given id
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if( len( args ) == 1 ):
			id = args[0]
		elif "id" in kwargs:
			id = kwargs["id"]
		else:
			raise errors.NotAcceptable()
		skel = self.editSkel()
		if  not self.canEdit( id ):
			raise errors.Unauthorized()
		if not skel.fromDB( id ):
			raise errors.NotAcceptable()
		if len(kwargs)==0 or skey=="" or not request.current.get().isPostRequest or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.edit( skel ) )
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		skel.toDB( id )
		self.onItemEdited( skel )
		return self.render.editItemSuccess( skel )


	@forceSSL
	@exposed
	def add( self, parent, *args, **kwargs ):
		"""
			Add a new entry with the given parent
			@param parent: Urlsafe-key of the parent
			@type parent: String
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if not self.isValidParent( parent ): #Ensure the parent exists
			raise errors.NotAcceptable()
		if not self.canAdd( parent ):
			raise errors.Unauthorized()
		skel = self.addSkel()
		if len(kwargs)==0 or skey=="" or not request.current.get().isPostRequest or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.add( skel ) )
		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()
		skel.parententry.value = str( parent )
		skel.parentrepo.value = str( self.getRootNode( parent ).key() )
		key = skel.toDB( )
		self.onItemAdded( skel )
		return self.render.addItemSuccess( skel )

## Default accesscontrol functions 

	def canAdd( self, parent ):
		"""
			Checks if the current user has the right to add a new child to the given parent
			@param parent: Urlsave-key of the parent under which the element get added
			@type parent: String
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user["access"] and "%s-add" % self.modulName in user["access"]:
			return( True )
		return( False )

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
		if user["access"] and ( "%s-edit" % self.modulName in user["access"] or "%s-add" % self.modulName in user["access"] ):
			return( True )
		return( False )
	
	def canEdit( self, key ):
		"""
			Checks if the current user has the right to edit the given entry
			@param id: Urlsafe-key of the entry
			@type id: String
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
		
	def canView( self, key ):
		"""
			Checks if the current user has the right to view the given entry
			@param id: Urlsafe-key of the entry
			@type id: String
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
		
	def canDelete( self, key ):
		"""
			Checks if the current user has the right to delete the given entry (and everything below)
			@param id: Urlsafe-key of the entry
			@type id: String
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user["access"] and "%s-delete" % self.modulName in user["access"]:
			return( True )
		return( False )

	def canSetIndex( self, item, index ):
		"""
			Checks if the current user can change the ordering of the given item
			@param item: Urlsafe-key of the entry
			@type item: String
			@param index: New sortindex for this item.
			@type index: Float
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user["access"] and ( "%s-edit" % self.modulName in user["access"] or "%s-add" % self.modulName in user["access"] ):
			return( True )
		return( False )
	
	def canList( self, parent ):
		"""
			Checks if the current user has the right to list the children of the given parent
			@param parent: Urlsave-key of the parent under which the element get added
			@type parent: String
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
	
	def canReparent( self, item, dest ):
		"""
			Checks if the current user has the right to move an element (including its children) to a new parent
			@param item: Urlsave-key of the item which will be moved
			@type item: String
			@param dest: Urlsave-key of the dest the item will be moved to
			@type dest: String
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

## Overridable eventhooks

	def onItemAdded( self, skel ):
		"""
			Hook. Can be overriden to hook the onItemAdded-Event
			@param id: Urlsafe-key of the entry added
			@type id: String
			@param skel: Skeleton with the data which has been added
			@type skel: Skeleton
		"""
		logging.info("Entry added: %s" % skel.id.value )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
	
	def onItemEdited( self, skel ):
		"""
			Hook. Can be overriden to hook the onItemEdited-Event
			@param id: Urlsafe-key of the entry added
			@type id: String
			@param skel: Skeleton with the data which has been edited
			@type skel: Skeleton
		"""
		logging.info("Entry changed: %s" % skel.id.value )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
		
	def onItemViewed( self, key, skel ):
		"""
			Hook. Can be overriden to hook the onItemViewed-Event
			@param id: Urlsafe-key of the entry added
			@type id: String
			@param skel: Skeleton with the data which has been viewed
			@type skel: Skeleton
		"""
		pass
	
	def onItemDeleted( self, skel ):
		"""
			Hook. Can be overriden to hook the onItemDeleted-Event
			Note: Saving the skeleton again will undo the deletion.
			@param id: Urlsafe-key of the entry deleted
			@type id: Skeleton
		"""
		logging.info("Entry deleted: %s" % skel.id.value )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )

Hierarchy.admin=True
Hierarchy.jinja2=True
Hierarchy.ops=True
