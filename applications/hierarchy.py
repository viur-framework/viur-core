# -*- coding: utf-8 -*-
from server import db, utils, errors, session, conf, request, securitykey
from server import forcePost, forceSSL, exposed, internalExposed

from server.applications import BasicApplication
from server.bones import baseBone, numericBone
from server.tasks import callDeferred
from server.skeleton import Skeleton

from time import time
from datetime import datetime
import logging

class HierarchySkel(Skeleton):
	parententry = baseBone( descr="Parent", visible=False, indexed=True, readOnly=True )
	parentrepo = baseBone( descr="BaseRepo", visible=False, indexed=True, readOnly=True )
	sortindex = numericBone( descr="SortIndex", mode="float", visible=False, indexed=True, readOnly=True )
	
	def preProcessSerializedData( self, dbfields ):
		if not ("sortindex" in dbfields.keys() and dbfields["sortindex"] ):
			dbfields[ "sortindex" ] = time()
		return dbfields

	def refresh(self):
		if self["parententry"].value:
			self["parententry"].value = utils.normalizeKey(self["parententry"].value)
		if self["parentrepo"].value:
			self["parentrepo"].value = utils.normalizeKey(self["parentrepo"].value)
		super( HierarchySkel, self ).refresh()



class Hierarchy(BasicApplication):
	"""
	Hierarchy is a ViUR BasicApplication.

	It is used for multiple data entities of the same kind, which are stored in an hierarchical order.
	Every element of the hierarchy can be a child of another element or may contain more children.
	It needs to be sub-classed for individual modules.

	:ivar kindName: Name of the kind of data entities that are managed by the application. \
	This information is used to bind a specific :class:`server.skeleton.Skeleton`-class to the \
	application. For more information, refer to the function :func:`_resolveSkel`.
	:vartype kindName: str

	:ivar adminInfo: todo short info on how to use adminInfo.
	:vartype adminInfo: dict | callable
	"""

	accessRights = ["add", "edit", "view", "delete"]# Possible access rights for this app

	def adminInfo(self):
		return {
			"name": self.__class__.__name__,        # Module name as shown in the admin tools
			"handler": "hierarchy",                 # Which handler to invoke
			"icon": "icons/modules/hierarchy.svg"   # Icon for this module
		}

	def __init__( self, modulName, modulPath, *args, **kwargs ):
		super(Hierarchy, self).__init__(modulName, modulPath, *args, **kwargs)

	def viewSkel( self, *args, **kwargs ):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for viewing an existing entry from the hierarchy.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`addSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for viewing an entry.
		:rtype: server.skeleton.Skeleton
		"""
		return self._resolveSkel(*args, **kwargs)

	def addSkel( self, *args, **kwargs ):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for adding an entry to the hierarchy.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for adding an entry.
		:rtype: server.skeleton.Skeleton
		"""
		return self._resolveSkel(*args, **kwargs)

	def editSkel( self, *args, **kwargs ):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for editing an existing entry from the hierarchy.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for editing an entry.
		:rtype: server.skeleton.Skeleton
		"""
		return self._resolveSkel(*args, **kwargs)

	def getRootNode(self, entryKey ):
		"""
		Returns the root-node for a given child.

		:param entryKey: URL-Safe key of the child entry
		:type entryKey: str

		:returns: The entity of the root-node.
		:rtype: :class:`server.db.Entity`
		"""
		repo = db.Get( entryKey )
		while repo and "parententry" in repo.keys():
			repo = db.Get( repo["parententry"] )

		assert repo and repo.key().kind() == self.viewSkel().kindName+"_rootNode"
		return repo

	def isValidParent(self, parent ):
		"""
		Checks wherever a given parent is valid.
		
		:param parent: Parent to test
		:type parent: str

		:returns: Test result.
		:rtype: bool
		"""
		if self.viewSkel().fromDB( parent ): #Its a normal node
			return True

		try:
			assert self.getRootNode( parent )
			return True  #Its a rootNode :)
		except:
			pass

		return False

	def ensureOwnUserRootNode( self ):
		"""
		Ensures, that an root-node for the current user exists.
		If no root-node exists yet, it will be created.

		:returns: The entity of the root-node or None, if this was request was made by a guest.
		:rtype: :class:`server.db.Entity`
		"""
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if thisuser:
			key = "rep_user_%s" % str( thisuser["id"] )
			kindName = self.viewSkel().kindName+"_rootNode"
			return db.GetOrInsert(key, kindName=kindName, creationdate=datetime.now(),
			                        rootNode=1, user=str( thisuser["id"] ) )

		return None

	def ensureOwnModulRootNode( self ):
		"""
		Ensures, that general root-node for the current module exists.
		If no root-node exists yet, it will be created.

		:returns: The entity of the root-node.
		:rtype: :class:`server.db.Entity`
		"""
		key = "rep_modul_repo"
		kindName = self.viewSkel().kindName+"_rootNode"
		return db.GetOrInsert( key, kindName=kindName, creationdate=datetime.now(), rootNode=1 )

	def isOwnUserRootNode( self, repo ):
		"""
		Checks, if the given rootNode is owned by the current user.

		:param repo: URL-safe key of the root-node.
		:type repo: str

		:returns: True if the user owns this root-node, False otherwise.
		:rtype: bool
		"""
		thisuser = utils.getCurrentUser()
		if not thisuser:
			return False

		repo = self.getRootNode( repo )
		user_repo = self.ensureOwnUserRootNode()

		if str( repo.key.urlsafe() ) == user_repo.key.urlsafe():
			return True

		return False

	def deleteRecursive( self, key ):
		"""
		Recursively processes a delete request.

		This will delete all entries which are children of *key*, except *key* itself.

		:param key: URL-safe key of the node which children should be deleted.
		:type key: str

		:returns: The number of deleted objects.
		:rtype: int
		"""
		count = 0
		entrys = db.Query( self.viewSkel().kindName ).filter( "parententry", str(key) ).run()

		for e in entrys:
			count += self.deleteRecursive(str(e.key()))
			vs = self.editSkel()
			vs.setValues(e, key=e.key())
			vs.delete()
			count += 1

		return count

## Internal exposed functions

	@internalExposed
	def pathToKey( self, key=None ):
		"""
		Returns the recursively expanded path through the Hierarchy from the root-node to a
		requested node.

		:param key: URL-safe key of the destination entity.
		:type key: str

		:returns: An nested dictionary with information about all nodes in the path from root \
		to the requested node.
		:rtype: dict
		"""
		def getName( obj ):
			"""
				Tries to return a suitable name for the given object.
			"""
			if "name" in obj.keys():
				return obj["name"]

			skel = self.viewSkel()
			if "name" in skel.keys():
				nameBone = skel["name"]

				if (isinstance(nameBone, baseBone)
				    and "languages" in dir( nameBone )
				    and nameBone.languages):
					skel.setValues( obj )
					return unicode( skel["name"].value )

			return None
			
		availableRepos = self.getAvailableRootNodes()
		if not key:
			try:
				key = availableRepos[0]["key"]
			except:
				raise errors.NotFound()

			keylist = []
		else:
			if str(key).isdigit():
				key = str( db.Key.from_path( self.viewSkel().kindName, long(key) ) )
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

				r = {
						"name": getName( obj ),
						"id": str(obj.key()),
						"parent": parent,
						"hrk": obj["hrk"] if "hrk" in obj.keys() else None,
						"active":(str(obj.key()) in keylist)
				}

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

		return res

## External exposed functions

	@exposed
	def listRootNodes(self, *args, **kwargs ):
		"""
		Renders a list of all available repositories for the current user using the
		modules default renderer.

		:returns: The rendered representation of the available root-nodes.
		:rtype: str
		"""
		return self.render.listRootNodes( self.getAvailableRootNodes( *args, **kwargs ) )
		

	@exposed
	def preview( self, skey, *args, **kwargs ):
		"""
		Renders data for an entry, without reading from the database.
		This function allows to preview an entry without writing it to the database.

		Any entity values are provided via *kwargs*.

		The function uses the viewTemplate of the application.

		:returns: The rendered representation of the the supplied data.
		"""
		if not self.canPreview():
			raise errors.Unauthorized()

		if not securitykey.verify( skey ):
			raise errors.PreconditionFailed()

		skel = self.viewSkel()
		skel.fromClient( kwargs )

		return self.render.view( skel )


	@forceSSL
	@forcePost
	@exposed
	def reparent( self, item, dest, skey, *args, **kwargs ):
		"""
		Moves an entry *item* (and everything beneath it) to another parent-node *dest*.

		.. seealso:: :func:`canReparent`

		:param item: URL-safe key of the item which will be moved.
		:type item: str
		:param dest: URL-safe key of the new parent for this item.
		:type dest: str

		:returns: A rendered success result generated by the default renderer.

		:raises: :exc:`server.errors.NotFound`, when no entry with the given *id* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		if not self.canReparent( item, dest ):
			raise errors.Unauthorized()

		if not self.isValidParent( dest ) or item==dest:
			raise errors.NotAcceptable()

		## Test for recursion
		isValid = False
		currLevel = db.Get( dest )

		for x in range(0,99):
			if str(currLevel.key())==item:
				break

			if currLevel.key().kind() == self.viewSkel().kindName+"_rootNode":
				#We reached a rootNode
				isValid=True
				break

			currLevel = db.Get( currLevel["parententry"] )

		if not isValid:
			raise errors.NotAcceptable()

		## Update entry
		fromItem = db.Get( item )
		fromItem["parententry"] = dest 
		fromItem["parentrepo"] = str( self.getRootNode( dest ).key() )
		db.Put( fromItem )

		return self.render.reparentSuccess( obj=fromItem )

	
	@forceSSL
	@forcePost
	@exposed
	def setIndex( self, item, index, skey, *args, **kwargs ):
		"""
		Changes the order of the elements in the current level by changing the index of *item*.

		.. seealso:: :func:`canSetIndex`

		:param item: URL-safe key of the item which index should be changed.
		:type item: str

		:param index: New index for this item. This value must be cast-able to float.
		:type index: str

		:returns: A rendered success result generated by the default renderer.

		:raises: :exc:`server.errors.NotFound`, when no entry with the given *id* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		if not self.canSetIndex( item, index ):
			raise errors.Unauthorized()

		fromItem = db.Get( item )
		fromItem["sortindex"] = float( index )
		db.Put( fromItem )

		return self.render.setIndexSuccess( obj=fromItem )


	@forceSSL
	@forcePost
	@exposed
	def delete( self, id, skey, *args, **kwargs ):
		"""
		Delete an entry and all its children.

		The function runs several access control checks on the data before it is deleted.

		.. seealso:: :func:`canDelete`, :func:`editSkel`, :func:`onItemDeleted`

		:param id: URL-safe key of the entry to be deleted.
		:type id: str

		:returns: The rendered, deleted object of the entry.

		:raises: :exc:`server.errors.NotFound`, when no entry with the given *id* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		skel = self.editSkel()

		if not skel.fromDB( id ):
			raise errors.NotFound()

		if not self.canDelete( skel ):
			raise errors.Unauthorized()

		self.deleteRecursive( id )
		skel.delete()
		self.onItemDeleted( skel )

		return self.render.deleteSuccess( skel )


	@exposed
	def view( self, *args, **kwargs ):
		"""
		Prepares and renders a single entry for viewing.

		The entry is fetched by its entity key, which either is provided via *kwargs["id"]*,
		or as the first parameter in *args*. The function performs several access control checks
		on the requested entity before it is rendered.

		.. seealso:: :func:`viewSkel`, :func:`canView`, :func:`onItemViewed`

		:returns: The rendered representation of the requested entity.

		:raises: :exc:`server.errors.NotAcceptable`, when no *id* is provided.
		:raises: :exc:`server.errors.NotFound`, when no entry with the given *id* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		"""
		if "id" in kwargs:
			id = kwargs["id"]
		elif len( args ) >= 1:
			id = args[0]
		else:
			raise errors.NotAcceptable()
		if not len(id):
			raise errors.NotAcceptable()
		skel = self.viewSkel()

		if not skel.fromDB( id ):
			raise errors.NotFound()

		if not self.canView( skel ):
			raise errors.Unauthorized()

		self.onItemViewed( skel )
		return self.render.view( skel )


	@exposed
	def list( self, parent, *args, **kwargs ):
		"""
		List the entries which are direct children of the given *parent*.
		Any other supplied parameters are interpreted as filters for the elements displayed.

		.. seealso:: :func:`canList`, :func:`server.db.mergeExternalFilter`

		:param parent: URL-safe key of the parent.
		:type parent: str

		:returns: The rendered list objects for the matching entries.

		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.NotFound`, if *parent* could not be found.
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
		return self.render.list( query.fetch(), parent=parent, parentSkel=parentSkel )


	@forceSSL
	@exposed
	def edit( self, *args, **kwargs ):
		"""
		Modify an existing entry, and render the entry, eventually with error notes on incorrect data.
		Data is taken by any other arguments in *kwargs*.

		The entry is fetched by its entity key, which either is provided via *kwargs["id"]*,
		or as the first parameter in *args*. The function performs several access control checks
		on the requested entity before it is modified.

		.. seealso:: :func:`editSkel`, :func:`onItemEdited`, :func:`canEdit`

		:returns: The rendered, edited object of the entry, eventually with error hints.

		:raises: :exc:`server.errors.NotAcceptable`, when no *id* is provided.
		:raises: :exc:`server.errors.NotFound`, when no entry with the given *id* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""

		if len( args ) == 1:
			id = args[0]
		elif "id" in kwargs:
			id = kwargs["id"]
		else:
			raise errors.NotAcceptable()

		skel = self.editSkel()
		if not skel.fromDB( id ):
			raise errors.NotAcceptable()

		if  not self.canEdit( skel ):
			raise errors.Unauthorized()

		if (len(kwargs) == 0 # no data supplied
		    or skey == "" # no security key
		    or not request.current.get().isPostRequest # failure if not using POST-method
		    or not skel.fromClient( kwargs ) # failure on reading into the bones
		    or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1") # review before changing
		    ):
			return self.render.edit( skel )

		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		skel.toDB() # write it!
		self.onItemEdited( skel )

		return self.render.editItemSuccess( skel )


	@forceSSL
	@exposed
	def add( self, parent, *args, **kwargs ):
		"""
		Add a new entry with the given parent, and render the entry, eventually with error notes on incorrect data.
		Data is taken by any other arguments in *kwargs*.

		The function performs several access control checks on the requested entity before it is added.

		.. seealso:: :func:`addSkel`, :func:`onItemAdded`, :func:`canAdd`

		:param parent: URL-safe key of the parent.
		:type parent: str

		:returns: The rendered, added object of the entry, eventually with error hints.

		:raises: :exc:`server.errors.NotAcceptable`, when no valid *parent* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
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

		if (len(kwargs) == 0
		    or skey == ""
		    or not request.current.get().isPostRequest
		    or not skel.fromClient( kwargs )
		    or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1")
		    ):
			return self.render.add( skel )

		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()
		skel["parententry"].value = str( parent )
		skel["parentrepo"].value = str( self.getRootNode( parent ).key() )
		key = skel.toDB( )
		self.onItemAdded( skel )
		return self.render.addItemSuccess( skel )

	@forceSSL
	@exposed
	def clone(self, fromRepo, toRepo, fromParent = None, toParent = None, *args, **kwargs ):
		"""
		Clones a hierarchy recursively.

		This function only initiates the cloning process, which is performed in the background.
		It states only a successful result when the clone action has been correctly initiated.

		:param fromRepo: URL-safe key of the ID to the repository (=root-node ID) to clone from.
		:type fromRepo: str
		:param toRepo: URL-safe key of the ID to the repository (=root-node ID) to clone to.
		:type toRepo: str
		:param fromParent: URL-safe key of the parent to clone from; for root nodes, this is equal \
		 to fromRepo, and can be omitted.
		:type fromParent: str
		:param toParent: URL-safe key of the parent to clone to; for root nodes, this is equal to \
		toRepo, and can be omitted.
		:type toParent: str

		:returns: A rendered success result generated by the default renderer.

		:raises: :exc:`server.errors.NotAcceptable`, when no valid *parent* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""

		if fromParent is None:
			fromParent = fromRepo
		if toParent is None:
			toParent = toRepo

		if not (self.isValidParent(fromParent)
		        and self.isValidParent(toParent)): #Ensure the parents exists
			raise errors.NotAcceptable()

		if not self.canAdd( toParent ):
			raise errors.Unauthorized()
		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		self._clone( fromRepo, toRepo, fromParent, toParent )
		return self.render.cloneSuccess(*args, **kwargs)

	@callDeferred
	def _clone( self, fromRepo, toRepo, fromParent, toParent ):
		"""
		This is the internal cloning function that runs deferred and recursive.
		"""
		for node in self.viewSkel().all().filter("parententry =", fromParent).order("sortindex").run(99):
			old_id = str(node.key())

			skel = self.addSkel()
			skel.fromDB( old_id )

			for k,v in skel.items():
				logging.debug( "BEFORE %s = >%s<", ( k, v.value ) )

			skel = skel.clone()
			#skel.setValues( {}, key=None )

			for k,v in skel.items():
				logging.debug( "BEHIND %s = >%s<", ( k, v.value ) )

			skel[ "parententry" ].value = toParent
			skel[ "parentrepo" ].value = toRepo

			new_id = skel.toDB()
			self._clone( fromRepo, toRepo, old_id, new_id )

## Default accesscontrol functions 

	def canAdd( self, parent ):
		"""
		Access control function for adding permission.

		Checks if the current user has the permission to add a new entry to *parent*.

		The default behavior is:
		- If no user is logged in, adding is generally refused.
		- If the user has "root" access, adding is generally allowed.
		- If the user has the modules "add" permission (module-add) enabled, adding is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`add`

		:param parent: URL-safe key of the parent node under which the element shall be added.
		:type parent: str

		:returns: True, if adding entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user["access"] and "%s-add" % self.modulName in user["access"]:
			return True

		return False

	def canPreview( self ):
		"""
		Access control function for preview permission.

		Checks if the current user has the permission to preview an entry.

		The default behavior is:
		- If no user is logged in, previewing is generally refused.
		- If the user has "root" access, previewing is generally allowed.
		- If the user has the modules "add" or "edit" permission (module-add, module-edit) enabled, \
		previewing is allowed.

		It should be overridden for module-specific behavior.

		.. seealso:: :func:`preview`

		:returns: True, if previewing entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user["access"] and ( "%s-edit" % self.modulName in user["access"]
		                        or "%s-add" % self.modulName in user["access"] ):
			return True

		return False
	
	def canEdit( self, skel ):
		"""
		Access control function for modification permission.

		Checks if the current user has the permission to edit an entry.

		The default behavior is:
		- If no user is logged in, editing is generally refused.
		- If the user has "root" access, editing is generally allowed.
		- If the user has the modules "edit" permission (module-edit) enabled, editing is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`edit`

		:param skel: The Skeleton that should be edited.
		:type skel: :class:`server.skeleton.Skeleton`

		:returns: True, if editing entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user["access"] and "%s-edit" % self.modulName in user["access"]:
			return True

		return False
		
	def canView( self, skel ):
		"""
		Access control function for viewing permission.

		Checks if the current user has the permission to view an entry.

		The default behavior is:
		- If no user is logged in, viewing is generally refused.
		- If the user has "root" access, viewing is generally allowed.
		- If the user has the modules "view" permission (module-view) enabled, viewing is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`view`

		:param skel: The Skeleton that should be viewed.
		:type skel: :class:`server.skeleton.Skeleton`

		:returns: True, if viewing is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user["access"] and "%s-view" % self.modulName in user["access"]:
			return True

		return False
		
	def canDelete( self, skel ):
		"""
		Access control function for delete permission.

		Checks if the current user has the permission to delete an entry.

		The default behavior is:
		- If no user is logged in, deleting is generally refused.
		- If the user has "root" access, deleting is generally allowed.
		- If the user has the modules "deleting" permission (module-delete) enabled, \
		 deleting is allowed.

		It should be overridden for a module-specific behavior.

		:param skel: The Skeleton that should be deleted.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`delete`

		:returns: True, if deleting entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user["access"] and "%s-delete" % self.modulName in user["access"]:
			return True

		return False

	def canSetIndex( self, item, index ):
		"""
		Access control function for changing order permission.

		Checks if the current user has the permission to change the ordering of an entry.

		The default behavior is:
		- If no user is logged in, any modification is generally refused.
		- If the user has "root" access, modification is generally allowed.
		- If the user has the modules "edit" or "add" permission (module-edit, module-add) enabled, \
		 modification is allowed.

		It should be overridden for a module-specific behavior.

		:param item: URL-safe key of the entry.
		:type item: str
		:param item: New sortindex for this item.
		:type item: float

		.. seealso:: :func:`setIndex`

		:returns: True, if changing the order of entries is allowed, False otherwise.
		:rtype: bool
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
		Access control function for listing permission.

		Checks if the current user has the permission to list the children of the given *parent*.

		The default behavior is:
		- If no user is logged in, listing is generally refused.
		- If the user has "root" access, listing is generally allowed.
		- If the user has the modules "view" permission (module-view) enabled, listing is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`list`

		:param parent: URL-safe key of the parent.
		:type parent: str

		:returns: True, if listing is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user["access"] and "%s-view" % self.modulName in user["access"]:
			return True

		return False
	
	def canReparent( self, item, dest ):
		"""
		Access control function for item moving permission.

		Checks if the current user has the permission to move *item* to *dest*.

		The default behavior is:
		- If no user is logged in, any modification is generally refused.
		- If the user has "root" access, modification is generally allowed.
		- If the user has the modules "edit" permission (module-edit) enabled, moving is allowed.

		It should be overridden for a module-specific behavior.

		:param item: URL-safe key of the entry.
		:type item: str
		:param item: URL-safe key of the new parent to be moved to.
		:type item: float

		.. seealso:: :func:`reparent`

		:returns: True, if changing the order of entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user["access"] and "%s-edit" % self.modulName in user["access"]:
			return True

		return False

## Overridable eventhooks

	def onItemAdded( self, skel ):
		"""
		Hook function that is called after adding an entry.

		It should be overridden for a module-specific behavior.
		The default is writing a log entry.

		:param skel: The Skeleton that has been added.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`add`
		"""
		logging.info("Entry added: %s" % skel["id"].value )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
	
	def onItemEdited( self, skel ):
		"""
		Hook function that is called after modifying an entry.

		It should be overridden for a module-specific behavior.
		The default is writing a log entry.

		:param skel: The Skeleton that has been modified.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`edit`
		"""
		logging.info("Entry changed: %s" % skel["id"].value )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
		
	def onItemViewed( self, skel ):
		"""
		Hook function that is called when viewing an entry.

		It should be overridden for a module-specific behavior.
		The default is doing nothing.

		:param skel: The Skeleton that is viewed.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`view`
		"""
		pass
	
	def onItemDeleted( self, skel ):
		"""
		Hook function that is called after deleting an entry.

		It should be overridden for a module-specific behavior.
		The default is writing a log entry.

		:param skel: The Skeleton that has been deleted.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`delete`
		"""
		logging.info("Entry deleted: %s" % skel["id"].value )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )

## Renderer specific stuff

	def jinjaEnv(self, env ):
		"""
		Provides some additional Jinja2 template functions for hierarchy applications.

		These function are:

		- :func:`pathToKey()` alias *getPathToKey()*
		- :func:`canAdd()`
		- :func:`canPreview()`
		- :func:`canEdit()`
		- :func:`canView()`
		- :func:`canDelete()`
		- :func:`canSetIndex()`
		- :func:`canList()`
		- :func:`canReparent()`

		..warning::
		It is important to call the super-class-function of Hierarchy when this function
		is overridden from a sub-classed module.
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

		return env

Hierarchy.admin=True
Hierarchy.jinja2=True
Hierarchy.vi=True
