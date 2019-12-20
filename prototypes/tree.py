# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from viur.core import conf, db, errors, exposed, forcePost, forceSSL, internalExposed, securitykey, utils
from viur.core.bones import keyBone
from viur.core.prototypes import BasicApplication
from viur.core.skeleton import Skeleton
from viur.core.tasks import callDeferred


class TreeLeafSkel(Skeleton):
	parentdir = keyBone(descr="Parent", indexed=True)
	parentrepo = keyBone(descr="BaseRepo", indexed=True)

	def fromDB(self, *args, **kwargs):
		res = super(TreeLeafSkel, self).fromDB(*args, **kwargs)

		# Heal missing parent-repo values
		if res and not self["parentrepo"]:
			try:
				dbObj = db.Get(self["key"])
			except:
				return res

			if not "parentdir" in dbObj:  # RootNode
				return res

			while ("parentdir" in dbObj and dbObj["parentdir"]):
				try:
					dbObj = db.Get(dbObj["parentdir"])
				except:
					return res

			self["parentrepo"] = str(dbObj.key())
			self.toDB()

		return res


class TreeNodeSkel(TreeLeafSkel):
	pass


class Tree(BasicApplication):
	"""
	Tree is a ViUR BasicApplication.

	In this application, entries are hold in directories, which can be nested. Data in a Tree application
	always consists of nodes (=directories) and leafs (=files).

	:ivar kindName: Name of the kind of data entities that are managed by the application. \
	This information is used to bind a specific :class:`server.skeleton.Skeleton`-class to the \
	application. For more information, refer to the function :func:`_resolveSkel`.\
	\
	In difference to the other ViUR BasicApplication, the kindName in Trees evolve into the kindNames\
	*kindName + "node"* and *kindName + "leaf"*, because information can be stored in different kinds.

	:ivar adminInfo: todo short info on how to use adminInfo.
	:vartype adminInfo: dict | callable
	"""

	accessRights = ["add", "edit", "view", "delete"]  # Possible access rights for this app

	def adminInfo(self):
		return {
			"name": self.__class__.__name__,  # Module name as shown in the admin tools
			"handler": "tree",  # Which handler to invoke
			"icon": "icons/modules/tree.svg"  # Icon for this module
		}

	def __init__(self, moduleName: str, modulePath: str):
		super(Tree, self).__init__(moduleName, modulePath)

	@callDeferred
	def deleteRecursive(self, nodeKey):
		"""
		Recursively processes a delete request.

		This will delete all entries which are children of *nodeKey*, except *key* nodeKey.

		:param key: URL-safe key of the node which children should be deleted.
		:type key: str
		"""

		for f in db.Query(self.viewLeafSkel().kindName).filter("parentdir", str(nodeKey)).iter(keysOnly=True):
			s = self.viewLeafSkel()
			if not s.fromDB(f):
				continue
			s.delete()
		for d in db.Query(self.viewNodeSkel().kindName).filter("parentdir", str(nodeKey)).iter(keysOnly=True):
			count += self.deleteRecursive(str(d))
			self.deleteRecursive(str(d))
			s = self.viewNodeSkel()
			if not s.fromDB(d):
				continue
			s.delete()

	@callDeferred
	def updateParentRepo(self, parentNode, newRepoKey, depth=0):
		"""
		Recursively fixes the parentrepo key after a move operation.

		This will delete all entries which are children of *nodeKey*, except *key* nodeKey.

		:param parentNode: URL-safe key of the node which children should be fixed.
		:type parentNode: str
		:param newNode: URL-safe key of the new repository.
		:type newNode: strg
		:param depth: Safety level depth preventing infinitive loops.
		:type depth: int
		"""
		if depth > 99:
			logging.critical("Maximum recursion depth reached in server.applications.tree/fixParentRepo")
			logging.critical("Your data is corrupt!")
			logging.critical("Params: parentNode: %s, newRepoKey: %s" % (parentNode, newRepoKey))
			return

		def fixTxn(nodeKey, newRepoKey):
			node = db.Get(nodeKey)
			node["parentrepo"] = newRepoKey
			db.Put(node)

		# Fix all nodes
		for repo in db.Query(self.viewNodeSkel().kindName).filter("parentdir =", parentNode).iter(keysOnly=True):
			self.updateParentRepo(str(repo), newRepoKey, depth=depth + 1)
			db.RunInTransaction(fixTxn, str(repo), newRepoKey)

		# Fix the leafs on this level
		for repo in db.Query(self.viewLeafSkel().kindName).filter("parentdir =", parentNode).iter(keysOnly=True):
			db.RunInTransaction(fixTxn, str(repo), newRepoKey)

	## Internal exposed functions

	@internalExposed
	def pathToKey(self, key):
		"""
		Returns the recursively expanded path through the Tree from the root-node to the given *key*.

		:param key: URL-safe key of the destination node.
		:type key: str

		:returns: An nested dictionary with information about all nodes in the path from root to the \
		given node key.
		:rtype: dict
		"""
		nodeSkel = self.viewNodeSkel()

		if not nodeSkel.fromDB(key):
			raise errors.NotFound()

		if not self.canList("node", key):
			raise errors.Unauthorized()

		res = [self.render.collectSkelData(nodeSkel)]

		for x in range(0, 99):
			if not nodeSkel["parentdir"]:
				break

			parentdir = nodeSkel["parentdir"]

			nodeSkel = self.viewNodeSkel()
			if not nodeSkel.fromDB(parentdir):
				break

			res.append(self.render.collectSkelData(nodeSkel))

		return (res[:: -1])

	def ensureOwnUserRootNode(self):
		"""
		Ensures, that an root-node for the current user exists.
		If no root-node exists yet, it will be created.

		:returns: The entity of the root-node or None, if this was request was made by a guest.
		:rtype: :class:`server.db.Entity`
		"""
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if thisuser:
			key = "rep_user_%s" % str(thisuser["key"][1])
			return db.GetOrInsert((self.viewLeafSkel().kindName + "_rootNode", key),
								  creationdate=datetime.now(), rootNode=1, user=str(thisuser["key"]))

	def ensureOwnModuleRootNode(self):
		"""
		Ensures, that general root-node for the current module exists.
		If no root-node exists yet, it will be created.

		:returns: The entity of the root-node.
		:rtype: :class:`server.db.Entity`
		"""
		key = "rep_module_repo"
		return db.GetOrInsert((self.viewLeafSkel().kindName + "_rootNode", key),
							  creationdate=datetime.now(), rootNode=1)

	def getRootNode(self, subRepo):
		"""
		Returns the root-root-node for a given (sub)-repo.

		:param subRepo: URL-safe root-node key.
		:type subRepo: str

		:returns: :class:`server.db.Entity`
		"""
		kindName = self.viewNodeSkel().kindName
		repo = db.Get((kindName, subRepo))
		if not repo:
			return None
		if "parentrepo" in repo:
			return db.Get((kindName, repo["parentrepo"]))
		elif "rootNode" in repo and str(repo["rootNode"]) == "1":
			return repo
		return None

	def isOwnUserRootNode(self, repo):
		"""
		Checks, if the given rootNode is owned by the current user.

		:param repo: URL-safe key of the root-node.
		:type repo: str
		:returns: True if the user owns this root-node, False otherwise.
		:rtype: bool
		"""
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if not thisuser:
			return False

		repo = self.getRootNode(repo)

		user_repo = self.ensureOwnUserRootNode()
		if str(repo.key()) == str(user_repo.key()):
			return True

		return False

	## External exposed functions

	@exposed
	def listRootNodes(self, name=None, *args, **kwargs):
		"""
		Renders a list of all available repositories for the current user using the
		modules default renderer.

		:returns: The rendered representation of the available root-nodes.
		:rtype: str
		"""
		return self.render.listRootNodes(self.getAvailableRootNodes(name))

	@exposed
	def list(self, skelType, node, *args, **kwargs):
		"""
		List the entries and directories of the given *skelType* under the given *node*.
		Any other supplied parameters are interpreted as filters for the elements displayed.

		.. seealso:: :func:`canList`, :func:`server.db.mergeExternalFilter`

		:param skelType: May either be "node" or "leaf".
		:type skelType: str
		:param node: URL-safe key of the parent.
		:type node: str

		:returns: The rendered list objects for the matching entries.

		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.NotFound`, if *node* could not be found.
		:raises: :exc:`server.errors.NotAcceptable`, if anything else than "node" or "leaf" is provided to *skelType*.
		"""
		if skelType == "node":
			skel = self.viewNodeSkel()
		elif skelType == "leaf":
			skel = self.viewLeafSkel()
		else:
			raise errors.NotAcceptable()

		if skel is None:
			raise errors.NotAcceptable()

		if not self.canList(skelType, node):
			raise errors.Unauthorized()

		nodeSkel = self.viewNodeSkel()
		if not nodeSkel.fromDB(node):
			raise errors.NotFound()

		query = skel.all()

		if "search" in kwargs and kwargs["search"]:
			query.filter("parentrepo =", str(nodeSkel["key"]))
		else:
			query.filter("parentdir =", str(nodeSkel["key"]))

		query.mergeExternalFilter(kwargs)
		res = query.fetch()

		return self.render.list(res, node=str(nodeSkel["key"]))

	@exposed
	def view(self, skelType, key, *args, **kwargs):
		"""
		Prepares and renders a single entry for viewing.

		The entry is fetched by its *key* and its *skelType*.
		The function performs several access control checks on the requested entity before it is rendered.

		.. seealso:: :func:`canView`, :func:`onItemViewed`

		:returns: The rendered representation of the requested entity.

		:param skelType: May either be "node" or "leaf".
		:type skelType: str
		:param node: URL-safe key of the parent.
		:type node: str

		:raises: :exc:`server.errors.NotAcceptable`, when an incorrect *skelType* is provided.
		:raises: :exc:`server.errors.NotFound`, when no entry with the given *key* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		"""

		if skelType == "node":
			skel = self.viewNodeSkel()
		elif skelType == "leaf":
			skel = self.viewLeafSkel()
		else:
			raise errors.NotAcceptable()
		if skel is None:
			raise errors.NotAcceptable()
		if not len(key):
			raise errors.NotAcceptable()
		if key == u"structure":
			# We dump just the structure of that skeleton, including it's default values
			if not self.canView(skelType, None):
				raise errors.Unauthorized()
		else:
			# We return a single entry for viewing
			if not skel.fromDB(key):
				raise errors.NotFound()
			if not self.canView(skelType, skel):
				raise errors.Unauthorized()
			self.onItemViewed(skel)
		return self.render.view(skel)

	@exposed
	@forceSSL
	def add(self, skelType, node, *args, **kwargs):
		"""
		Add a new entry with the given parent *node*, and render the entry, eventually with error notes
		on incorrect data. Data is taken by any other arguments in *kwargs*.

		The function performs several access control checks on the requested entity before it is added.

		.. seealso:: :func:`onItemAdded`, :func:`canAdd`

		:param skelType: Defines the type of the new entry and may either be "node" or "leaf".
		:type skelType: str
		:param node: URL-safe key of the parent.
		:type node: str

		:returns: The rendered, added object of the entry, eventually with error hints.

		:raises: :exc:`server.errors.NotAcceptable`, when no valid *skelType* was provided.
		:raises: :exc:`server.errors.NotFound`, when no valid *node* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""

		if skelType == "node":
			skel = self.addNodeSkel()
		elif skelType == "leaf":
			skel = self.addLeafSkel()
		else:
			raise errors.NotAcceptable()

		parentNodeSkel = self.editNodeSkel()

		if not parentNodeSkel.fromDB(node):
			raise errors.NotFound()

		if not self.canAdd(skelType, node):
			raise errors.Unauthorized()

		if (len(kwargs) == 0  # no data supplied
				or skey == ""  # no security key
				# or not request.current.get().isPostRequest fixme: POST-method check missing? # failure if not using POST-method
				or not skel.fromClient(kwargs)  # failure on reading into the bones
				or ("bounce" in kwargs and kwargs["bounce"] == "1")  # review before adding
		):
			return self.render.add(skel)

		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()

		skel["parentdir"] = str(node)
		skel["parentrepo"] = parentNodeSkel["parentrepo"] or str(node)

		skel.toDB()
		self.onItemAdded(skel)

		return self.render.addItemSuccess(skel)

	@exposed
	@forceSSL
	def edit(self, skelType, key, skey="", *args, **kwargs):
		"""
		Modify an existing entry, and render the entry, eventually with error notes on incorrect data.
		Data is taken by any other arguments in *kwargs*.

		The function performs several access control checks on the requested entity before it is added.

		.. seealso:: :func:`onItemAdded`, :func:`canEdit`

		:param skelType: Defines the type of the entry that should be modified and may either be "node" or "leaf".
		:type skelType: str
		:param key: URL-safe key of the item to be edited.
		:type key: str

		:returns: The rendered, modified object of the entry, eventually with error hints.

		:raises: :exc:`server.errors.NotAcceptable`, when no valid *skelType* was provided.
		:raises: :exc:`server.errors.NotFound`, when no valid *node* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if skelType == "node":
			skel = self.editNodeSkel()
		elif skelType == "leaf":
			skel = self.editLeafSkel()
		else:
			raise errors.NotAcceptable()

		if not skel.fromDB(key):
			raise errors.NotFound()

		if not self.canEdit(skelType, skel):
			raise errors.Unauthorized()

		if (len(kwargs) == 0  # no data supplied
				or skey == ""  # no security key
				# or not request.current.get().isPostRequest fixme: POST-method check missing?  # failure if not using POST-method
				or not skel.fromClient(kwargs)  # failure on reading into the bones
				or ("bounce" in kwargs and kwargs["bounce"] == "1")  # review before adding
		):
			return self.render.edit(skel)

		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()

		skel.toDB()
		self.onItemEdited(skel)

		return self.render.editItemSuccess(skel)

	@exposed
	@forceSSL
	@forcePost
	def delete(self, skelType, key, *args, **kwargs):
		"""
		Deletes an entry or an directory (including its contents).

		The function runs several access control checks on the data before it is deleted.

		.. seealso:: :func:`canDelete`, :func:`onItemDeleted`

		:param skelType: Defines the type of the entry that should be deleted and may either be "node" or "leaf".
		:type skelType: str
		:param key: URL-safe key of the item to be deleted.
		:type key: str

		:returns: The rendered, deleted object of the entry.

		:raises: :exc:`server.errors.NotFound`, when no entry with the given *key* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
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

		if not skel.fromDB(key):
			raise errors.NotFound()

		if not self.canDelete(skelType, skel):
			raise errors.Unauthorized()
		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()

		if skelType == "node":
			self.deleteRecursive(key)
		skel.delete()

		self.onItemDeleted(skel)
		return self.render.deleteSuccess(skel, skelType=skelType)

	@exposed
	@forceSSL
	@forcePost
	def move(self, skelType, key, destNode, *args, **kwargs):
		"""
		Move a node (including its contents) or a leaf to another node.

		.. seealso:: :func:`canMove`

		:param skelType: Defines the type of the entry that should be moved and may either be "node" or "leaf".
		:type skelType: str
		:param key: URL-safe key of the item to be moved.
		:type key: str
		:param destNode: URL-safe key of the destination node, which must be a node.
		:type destNode: str

		:returns: The rendered, edited object of the entry.

		:raises: :exc:`server.errors.NotFound`, when no entry with the given *key* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if skelType == "node":
			srcSkel = self.editNodeSkel()
		elif skelType == "leaf":
			srcSkel = self.editLeafSkel()
		else:
			raise errors.NotAcceptable()

		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""

		destSkel = self.editNodeSkel()
		if not self.canMove(skelType, key, destNode):
			raise errors.Unauthorized()

		if key == destNode:
			# Cannot move a node into itself
			raise errors.NotAcceptable()

		## Test for recursion
		isValid = False
		currLevel = db.Get(destNode)

		for x in range(0, 99):
			if str(currLevel.key()) == key:
				break
			if "rootNode" in currLevel and currLevel["rootNode"] == 1:
				# We reached a rootNode
				isValid = True
				break
			currLevel = db.Get(currLevel["parentdir"])

		if not isValid:
			raise errors.NotAcceptable()

		# Test if key points to a rootNone
		tmp = db.Get(key)

		if "rootNode" in tmp and tmp["rootNode"] == 1:
			# Cant move a rootNode away..
			raise errors.NotAcceptable()

		if not srcSkel.fromDB(key) or not destSkel.fromDB(destNode):
			# Could not find one of the entities
			raise errors.NotFound()

		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()

		srcSkel["parentdir"] = str(destNode)
		srcSkel["parentrepo"] = destSkel["parentrepo"]  # Fixme: Need to recursive fixing to parentrepo?
		srcSkel.toDB()
		self.updateParentRepo(key, destSkel["parentrepo"])

		return self.render.editItemSuccess(srcSkel, skelType=skelType, action="move", destNode=destSkel)

	## Default accesscontrol functions

	def canList(self, skelType, node):
		"""
		Access control function for listing permission.

		Checks if the current user has the permission to list the children of the given *node*.

		The default behavior is:
		- If no user is logged in, listing is generally refused.
		- If the user has "root" access, listing is generally allowed.
		- If the user has the modules "view" permission (module-view) enabled, listing is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`list`

		:param skelType: Defines the type of node.
		:type skelType: str
		:param node: URL-safe key of the node.
		:type node: str

		:returns: True, if listing is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user and user["access"] and "%s-view" % self.moduleName in user["access"]:
			return True

		return False

	def canView(self, skelType, skel):
		"""
		Access control function for viewing permission.

		Checks if the current user has the permission to view *node*.

		The default behavior is:
		- If no user is logged in, viewing is generally refused.
		- If the user has "root" access, viewing is generally allowed.
		- If the user has the modules "view" permission (module-view) enabled, viewing is allowed.

		If skel is None, it's a check if the current user is allowed to retrieve the skeleton structure
		from this module (ie. there is or could be at least one entry that is visible to that user)

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`view`

		:param skelType: Defines the type of node.
		:type skelType: str
		:param skel: The Skeleton that should be viewed.
		:type skel: :class:`server.skeleton.Skeleton` | None

		:returns: True, if viewing is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user and user["access"] and "%s-view" % self.moduleName in user["access"]:
			return True

		return False

	def canAdd(self, skelType, node):
		"""
		Access control function for adding permission.

		Checks if the current user has the permission to add a new entry to *node*.

		The default behavior is:
		- If no user is logged in, adding is generally refused.
		- If the user has "root" access, adding is generally allowed.
		- If the user has the modules "add" permission (module-add) enabled, adding is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`add`

		:param skelType: Defines the type of the node that shall be added.
		:type skelType: str
		:param node: URL-safe key of the parent node under which the element shall be added.
		:type node: str

		:returns: True, if adding entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user and user["access"] and "%s-add" % self.moduleName in user["access"]:
			return True

		return False

	def canEdit(self, skelType, skel):
		"""
		Access control function for modification permission.

		Checks if the current user has the permission to edit an entry.

		The default behavior is:
		- If no user is logged in, editing is generally refused.
		- If the user has "root" access, editing is generally allowed.
		- If the user has the modules "edit" permission (module-edit) enabled, editing is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`edit`

		:param skelType: Defines the type of the node that shall be modified.
		:type skelType: str
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

		if user and user["access"] and "%s-edit" % self.moduleName in user["access"]:
			return True

		return False

	def canDelete(self, skelType, skel):
		"""
		Access control function for delete permission.

		Checks if the current user has the permission to delete an entry.

		The default behavior is:
		- If no user is logged in, deleting is generally refused.
		- If the user has "root" access, deleting is generally allowed.
		- If the user has the modules "deleting" permission (module-delete) enabled, \
		 deleting is allowed.

		It should be overridden for a module-specific behavior.

		:param skelType: Defines the type of the node that shall be deleted.
		:type skelType: str
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

		if user and user["access"] and "%s-delete" % self.moduleName in user["access"]:
			return True

		return False

	def canMove(self, skelType, node, destNode):
		"""
		Access control function for moving permission.

		Checks if the current user has the permission to move an entry.

		The default behavior is:
		- If no user is logged in, deleting is generally refused.
		- If the user has "root" access, deleting is generally allowed.
		- If the user has the modules "edit" permission (module-edit) enabled, \
		 moving is allowed.

		It should be overridden for a module-specific behavior.

		:param skelType: Defines the type of the node that shall be deleted.
		:type skelType: str
		:param node: URL-safe key of the node to be moved.
		:type node: str
		:param node: URL-safe key of the node where *node* should be moved to.
		:type node: str

		.. seealso:: :func:`move`

		:returns: True, if deleting entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return (False)
		if user["access"] and "root" in user["access"]:
			return (True)
		if user and user["access"] and "%s-edit" % self.moduleName in user["access"]:
			return (True)
		return (False)

	## Overridable eventhooks

	def onItemAdded(self, skel):
		"""
		Hook function that is called after adding an entry.

		It should be overridden for a module-specific behavior.
		The default is writing a log entry.

		:param skel: The Skeleton that has been added.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`add`
		"""
		logging.info("Entry added: %s" % skel["key"])
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["key"]))

	def onItemEdited(self, skel):
		"""
		Hook function that is called after modifying an entry.

		It should be overridden for a module-specific behavior.
		The default is writing a log entry.

		:param skel: The Skeleton that has been modified.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`edit`
		"""
		logging.info("Entry changed: %s" % skel["key"])
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["key"]))

	def onItemViewed(self, skel):
		"""
		Hook function that is called when viewing an entry.

		It should be overridden for a module-specific behavior.
		The default is doing nothing.

		:param skel: The Skeleton that is viewed.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`view`
		"""
		pass

	def onItemDeleted(self, skel):
		"""
		Hook function that is called after deleting an entry.

		It should be overridden for a module-specific behavior.
		The default is writing a log entry.

		..warning: Saving the skeleton again will undo the deletion
		(if the skeleton was a leaf or a node with no children).

		:param skel: The Skeleton that has been deleted.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`delete`
		"""
		logging.info("Entry deleted: %s (%s)" % (skel["key"], type(skel)))
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["key"]))

	## Renderer specific stuff

	def jinjaEnv(self, env):
		"""
		Provides some additional Jinja2 template functions for tree applications.

		These function are:

		- :func:`pathToKey()` alias *getPathToKey()*

		..warning::
		It is important to call the super-class-function of Hierarchy when this function
		is overridden from a sub-classed module.
		"""
		env.globals["getPathToKey"] = self.pathToKey
		return env


Tree.admin = True
Tree.html = True
Tree.vi = True
