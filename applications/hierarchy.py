# -*- coding: utf-8 -*-
from server.bones import baseBone, numericBone
from server.skeleton import Skeleton
from server.skellist import Skellist
from server import utils, errors, session, conf, request
from google.appengine.ext import ndb
from time import time
from google.appengine.api import users
from datetime import datetime
import logging

class HierarchySkel( Skeleton ):
	parententry = baseBone( descr="Parent", visible=False, readOnly=True )
	parentrepo = baseBone( descr="BaseRepo", visible=False, readonly=True )
	sortindex = numericBone( descr="SortIndex", mode="float", visible=False, readOnly=True )
	
	def preProcessSerializedData( self, dbfields ):
		if not ("sortindex" in dbfields.keys() and dbfields["sortindex"] ):
			dbfields[ "sortindex" ] = time()
		return( dbfields )
	
class CategorySkel( HierarchySkel ):
	pass

class Hierarchy( object ):
	""" 
		This application holds hierarchy data.
		In this application, entries are direct children of each other.
	"""
	
	
	adminInfo = {	"name": "BaseApplication", #Name of this modul, as shown in Apex (will be translated at runtime)
			"handler": "hierarchy",  #Which handler to invoke
			"icon": "", #Icon for this modul
			#,"orderby":"changedate",
			#"orderdir":1
			}
			
	def __init__( self, modulName, modulPath, *args, **kwargs ):
		self.modulName = modulName
		self.modulPath = modulPath
		if self.adminInfo and self.editSkel:
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

	def pathToKey( self, key=None ):
		"""
			Returns the recursively expaned Path through the Hierarchy from the RootNode to the given Node
			@param key: URlsafe Key of the destination node
			@type key: String:
			@returns: An nested dictionary with Informations about all nodes in the path from Root to the given Node
		"""
		availableRepos = self.getAvailableRootNodes()
		if not key:
			try:
				key = availableRepos[0]["key"]
			except:
				raise errors.NotFound()
			keylist = [ ]
		else:
			keylist = [ key ]
		if not self.canList( key ):
			raise errors.Unauthorized()
		res = []
		entryClass = utils.generateExpandoClass( self.viewSkel.entityName )
		lastChildren = []
		for x in range(0,99):
			entryObjs = entryClass.query().filter( ndb.GenericProperty("parententry") == str(key) ).order( ndb.GenericProperty("sortindex") ).fetch( 1000 )
			lastChildren = res[ : ]
			res = []
			for obj in entryObjs:
				if "parententry" in obj._properties.keys():
					parent = str( obj.parententry ) 
				else:
					parent = None
				r = {"name": obj.name,
					"id": str(obj.key.urlsafe()), 
					"hrk": obj.hrk, 
					"parent": parent,
					"active":(str(obj.key.urlsafe()) in keylist )}
				if r["active"]:
					r["children"] = lastChildren
				res.append( r )
			if key in [ x["key"] for x in availableRepos]:
				break
			else:
				item = ndb.Key( urlsafe=str( key ) ).get()
				if item and "parententry" in item._properties.keys():
					keylist.append( key )
					key = item.parententry
				else:
					break
		return( res )
	pathToKey.internalExposed=True

	def getRootNode(self, entryKey ):
		"""
			Returns the root for a given child.
			
			@parm entryKey: URL-Safe Key of thechild entry
			@type entryKey: string
			@returns: Entity
		"""
		repo = ndb.Key( urlsafe=entryKey ).get()
		while repo and  "parententry" in repo._properties.keys():
			repo = ndb.Key( urlsafe=repo.parententry ).get()
		assert repo and repo.key.kind() == self.viewSkel.entityName+"_rootNode"
		return( repo )

	def isValidParent(self, parent ):
		"""
		Checks wherever a given parent is valid.
		
		@param parent: Parent to test
		@type parent: String
		@returns: bool
		"""
		repoClass = utils.generateExpandoClass( self.viewSkel.entityName+"_rootNode" )
		try:
			if ndb.Key( urlsafe=parent ).get():
				return( True )
		except: #Might not be a rootNode -> wrong type
			pass
		if self.viewSkel().fromDB( parent ):
			return( True )
		return( False )

	def preview( self, skey, *args, **kwargs ):
		"""
			Renders the viewTemplate with the values given.
			This allows to preview an entry without having to save it first
		"""
		if not self.canPreview( ):
			raise errors.Unauthorized()
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		skel = self.viewSkel()
		skel.fromClient( kwargs )
		return( self.render.view( skel ) )
	preview.exposed = True

	def ensureOwnUserRootNode( self ):
		"""
			Ensures, that an rootNode for the current user exists.
			
			@returns: The Node-object (as ndb.Expando) or None, if this was request was made by a guest
		"""
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if thisuser:
			key = "rep_user_%s" % str( thisuser["id"] )
			return( utils.generateExpandoClass( self.viewSkel.entityName+"_rootNode" ).get_or_insert( key, creationdate=datetime.now(), rootNode=1, user=str( thisuser["id"] ) ) )


	def ensureOwnModulRootNode( self ):
		"""
			Ensures that the modul-global rootNode exists.
			
			@returns: The Node-object (as ndb.Expando)
		"""
		key = "rep_modul_repo"
		return( utils.generateExpandoClass( self.viewSkel.entityName+"_rootNode" ).get_or_insert( key, creationdate=datetime.now(), rootNode=1 ) )


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

	def listRootNodes(self, *args, **kwargs ):
		"""
			Renders a list of all available repositories for the current user
		"""
		return( self.render.listRootNodes( self.getAvailableRootNodes( *args, **kwargs ) ) )
	listRootNodes.exposed=True
	
	def reparent( self, item, dest, skey, *args, **kwargs ):
		"""
			Moves an entry (and everything beneath) to another parent-node.
			
			@param item: Urlsafe-key of the item which will be moved
			@type item: String
			@param dest: Urlsafe-key of the new parent for this item
			@type dest: String
		"""
		if not self.canReparent( item, dest ):
			raise errors.Unauthorized()
		if not self.isValidParent( dest ):
			raise errors.NotAcceptable()
		fromItem = ndb.Key( urlsafe=item ).get()
		fromItem.parententry = dest 
		fromItem.parentrepo = str( self.getRootNode( dest ).key.urlsafe() )
		fromItem.put()
		return( self.render.reparentSuccess( obj=fromItem ) )
	reparent.exposed = True
	reparent.forceSSL = True
	

	def setIndex( self, item, index, skey, *args, **kwargs ):
		"""
			Changes the order of the elements in the current level by changing the index of this item.
			@param item: Urlsafe-key of the item which index should be changed
			@type item: String
			@param index: New index for this item. Must be castable to float
			@type index: String
		"""
		if not self.canSetIndex( item, index ):
			raise errors.Unauthorized()
		fromItem = ndb.Key( urlsafe=item ).get()
		fromItem.sortindex = float( index )
		fromItem.put()
		return( self.render.setIndexSuccess( obj=fromItem ) )
	setIndex.exposed = True
	setIndex.forceSSL = True

	def delete( self, id, skey ):
		"""
			Delete an entry.
		"""
		if not self.canDelete( id ):
			raise errors.Unauthorized()
		self.deleteRecursive( id )
		self.onItemDeleted( id )
		return( self.render.deleteSuccess( id ) )
	delete.exposed = True
	delete.forceSSL = True

	def deleteRecursive( self, id ):
		"""
			Recursivly processes an delete request
		"""
		vs = self.viewSkel()
		entryClass = utils.generateExpandoClass( self.viewSkel.entityName )
		entrys = entryClass.query().filter( ndb.GenericProperty("parententry") == str(id) ).iter()
		for e in entrys:
			self.deleteRecursive( str( e.key.urlsafe() ) )
			vs.delete( str( e.key.urlsafe() ) )
		vs.delete( id )

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
		if str(id)!="0":
			if not skel.fromDB( id ):
				raise errors.NotFound()
		self.onItemViewed( id, skel )
		return( self.render.view( skel ) )
	view.exposed = True
	
	def list( self, parent, *args, **kwargs ):
		"""
			List the entries which are direct childs of the given parent
			@param parent: Urlsafe-key of the parent
			@type parent: String
		"""
		if not parent or not self.canList( parent ):
			raise errors.Unauthorized()
		mylist = Skellist( self.viewSkel )
		kwargs.update( **{ "parententry": parent } )
		queryObj = utils.buildDBFilter( self.viewSkel(), kwargs ) #Build the initial one
		mylist.fromDB( queryObj )
		return( self.render.list( mylist, parent=parent ) )
	list.exposed = True

	def edit( self, *args, **kwargs ):
		"""
			Edit the entry with the given id
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if( len( args ) == 1 ):
			id= args[0]
		elif "id" in kwargs:
			id = kwargs["id"]
		else:
			raise errors.NotAcceptable()
		skel = self.editSkel()
		if id == "0":
			return( self.render.edit( skel ) )
		if  not self.canEdit( id ):
			raise errors.Unauthorized()
		if not skel.fromDB( id ):
			raise errors.NotAcceptable()
		if len(kwargs)==0 or skey=="" or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.edit( skel ) )
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		skel.toDB( id )
		self.onItemAdded( id, skel )
		return self.render.editItemSuccess( skel )
	edit.exposed = True
	edit.forceSSL = True

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
		if not skel.fromClient( kwargs ) or len(kwargs)==0 or skey=="" or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.add( skel ) )
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		skel.parententry.value = str( parent )
		skel.parentrepo.value = str( self.getRootNode( parent ).key.urlsafe() )
		id = skel.toDB( )
		self.onItemAdded( id, skel )
		return self.render.addItemSuccess( id, skel )
	add.exposed = True
	add.forceSSL = True

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
	
	def canEdit( self, id ):
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
		
	def canView( self, id ):
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
		
	def canDelete( self, id ):
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

	def onItemAdded( self, id, skel ):
		"""
			Hook. Can be overriden to hook the onItemAdded-Event
			@param id: Urlsafe-key of the entry added
			@type id: String
			@param skel: Skeleton with the data which has been added
			@type skel: Skeleton
		"""
		logging.info("Entry added: %s" % id )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
	
	def onItemEdited( self, id, skel ):
		"""
			Hook. Can be overriden to hook the onItemEdited-Event
			@param id: Urlsafe-key of the entry added
			@type id: String
			@param skel: Skeleton with the data which has been edited
			@type skel: Skeleton
		"""
		logging.info("Entry changed: %s" % id )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
		
	def onItemViewed( self, id, skel ):
		"""
			Hook. Can be overriden to hook the onItemViewed-Event
			@param id: Urlsafe-key of the entry added
			@type id: String
			@param skel: Skeleton with the data which has been viewed
			@type skel: Skeleton
		"""
		pass
	
	def onItemDeleted( self, id ):
		"""
			Hook. Can be overriden to hook the onItemDeleted-Event
			Note: Saving the skeleton again will undo the deletion.
			@param id: Urlsafe-key of the entry deleted
			@type id: Skeleton
		"""
		logging.info("Entry deleted: %s" % id )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )

Hierarchy.admin=True
Hierarchy.jinja2=True
Hierarchy.ops=True
