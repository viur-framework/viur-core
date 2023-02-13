import logging
from typing import Any, Dict, List, Literal, Optional, Type, Union
from viur.core import utils, errors, conf, securitykey, db
from viur.core import forcePost, forceSSL, exposed, internalExposed
from viur.core.bones import KeyBone, SortIndexBone
from viur.core.cache import flushCache
from viur.core.prototypes import BasicApplication
from viur.core.skeleton import Skeleton, SkeletonInstance
from viur.core.tasks import CallDeferred
from viur.core.utils import currentRequest

SkelType = Literal["node", "leaf"]


class TreeSkel(Skeleton):
    parententry = KeyBone(
        descr="Parent",
        visible=False,
        readOnly=True,
    )
    parentrepo = KeyBone(
        descr="BaseRepo",
        visible=False,
        readOnly=True,
    )
    sortindex = SortIndexBone(
        visible=False,
        readOnly=True,
    )

    @classmethod
    def refresh(cls, skelValues):  # ViUR2 Compatibility
        super().refresh(skelValues)
        if not skelValues["parententry"] and skelValues.dbEntity.get("parentdir"):  # parentdir for viur2 compatibility
            skelValues["parententry"] = utils.normalizeKey(
                db.Key.from_legacy_urlsafe(skelValues.dbEntity["parentdir"]))


class Tree(BasicApplication):
    """
    Tree is a ViUR BasicApplication.

    In this application, entries are hold in directories, which can be nested. Data in a Tree application
    always consists of nodes (=directories) and leafs (=files).

    :ivar kindName: Name of the kind of data entities that are managed by the application. \
    This information is used to bind a specific :class:`viur.core.skeleton.Skeleton`-class to the \
    application. For more information, refer to the function :func:`_resolveSkel`.\
    \
    In difference to the other ViUR BasicApplication, the kindName in Trees evolve into the kindNames\
    *kindName + "node"* and *kindName + "leaf"*, because information can be stored in different kinds.
    :vartype kindName: str

    :ivar adminInfo: todo short info on how to use adminInfo.
    :vartype adminInfo: dict | callable
    """

    accessRights = ["add", "edit", "view", "delete"]  # Possible access rights for this app

    nodeSkelCls = None
    leafSkelCls = None

    def adminInfo(self):
        return {
            "name": self.__class__.__name__,  # Module name as shown in the admin tools
            "handler": "tree",  # Which handler to invoke
            "icon": "icon-hierarchy"  # Icon for this module
        }

    def __init__(self, moduleName, modulePath, *args, **kwargs):
        assert self.nodeSkelCls, "You have to specify at least nodeSkelCls for %r" % self.__class__.__name__
        super(Tree, self).__init__(moduleName, modulePath, *args, **kwargs)

    def _checkSkelType(self, skelType: Any) -> Optional[SkelType]:
        """
        Checks for correct skelType.

        Either returns the type provided, or None in case it is invalid.
        """
        skelType = skelType.lower()
        if skelType == "node" or (skelType == "leaf" and self.leafSkelCls):
            return skelType

        return None

    def _resolveSkelCls(self, skelType: SkelType, *args, **kwargs) -> Type[Skeleton]:
        if not (skelType := self._checkSkelType(skelType)):
            raise ValueError("Unsupported skelType")

        if skelType == "leaf":
            return self.leafSkelCls

        return self.nodeSkelCls

    def baseSkel(self, skelType: SkelType, *args, **kwargs) -> SkeletonInstance:
        """
        Return unmodified base skeleton for the given skelType.

        .. seealso:: :func:`addSkel`, :func:`editSkel`, :func:`viewSkel`, :func:`~baseSkel`
        """
        return self._resolveSkelCls(skelType, *args, **kwargs)()

    def viewSkel(self, skelType: SkelType, *args, **kwargs) -> SkeletonInstance:
        """
        Retrieve a new instance of a :class:`viur.core.skeleton.Skeleton` that is used by the application
        for viewing an existing entry from the list.

        The default is a Skeleton instance returned by :func:`~baseSkel`.

        .. seealso:: :func:`addSkel`, :func:`editSkel`, :func:`~baseSkel`

        :return: Returns a Skeleton instance for viewing an entry.
        """
        return self.baseSkel(skelType, *args, **kwargs)

    def addSkel(self, skelType: SkelType, *args, **kwargs) -> SkeletonInstance:
        """
        Retrieve a new instance of a :class:`viur.core.skeleton.Skeleton` that is used by the application
        for adding an entry to the list.

        The default is a Skeleton instance returned by :func:`~baseSkel`.

        .. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`~baseSkel`

        :return: Returns a Skeleton instance for adding an entry.
        """
        return self.baseSkel(skelType, *args, **kwargs)

    def editSkel(self, skelType: SkelType, *args, **kwargs) -> SkeletonInstance:
        """
        Retrieve a new instance of a :class:`viur.core.skeleton.Skeleton` that is used by the application
        for editing an existing entry from the list.

        The default is a Skeleton instance returned by :func:`~baseSkel`.

        .. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`~baseSkel`

        :return: Returns a Skeleton instance for editing an entry.
        """
        return self.baseSkel(skelType, *args, **kwargs)

    def ensureOwnModuleRootNode(self) -> db.Entity:
        """
        Ensures, that general root-node for the current module exists.
        If no root-node exists yet, it will be created.

        :returns: The entity of the root-node.
        """
        key = "rep_module_repo"
        kindName = self.viewSkel("node").kindName
        return db.GetOrInsert(db.Key(kindName, key), creationdate=utils.utcNow(), rootNode=1)

    def getAvailableRootNodes(self, *args, **kwargs) -> List[Dict[Literal["name", "key"], str]]:
        """
        Default function for providing a list of root node items.
        This list is requested by several module-internal functions and *must* be
        overridden by a custom functionality. The default stub for this function
        returns an empty list.
        An example implementation could be the following:
        .. code-block:: python

                    def getAvailableRootNodes(self, *args, **kwargs):
                        q = db.Query(self.rootKindName)
                            ret = [{"key": str(e.key()),
                                "name": e.get("name", str(e.key().id_or_name()))} #FIXME
                                for e in q.run(limit=25)]
                            return ret

        :param args: Can be used in custom implementations.
        :param kwargs: Can be used in custom implementations.
        :return: Returns a list of dicts which must provide a "key" and a "name" entry with \
                    respective information.
        """
        return []

    def getRootNode(self, entryKey: str) -> SkeletonInstance:
        """
        Returns the root-node for a given child.

        :param entryKey: URL-Safe key of the child entry

        :returns: The entity of the root-node.
        """
        rootNodeSkel = self.nodeSkelCls()
        entryKey = db.keyHelper(entryKey, rootNodeSkel.kindName)
        repo = db.Get(entryKey)
        while repo and "parententry" in repo:
            repo = db.Get(repo["parententry"])
        rootNodeSkel.fromDB(repo.key)
        return rootNodeSkel

    @CallDeferred
    def updateParentRepo(self, parentNode: str, newRepoKey: str, depth: int = 0):
        """
        Recursively fixes the parentrepo key after a move operation.

        This will delete all entries which are children of *nodeKey*, except *key* nodeKey.

        :param parentNode: URL-safe key of the node which children should be fixed.
        :param newRepoKey: URL-safe key of the new repository.
        :param depth: Safety level depth preventing infinitive loops.
        """
        if depth > 99:
            logging.critical("Maximum recursion depth reached in %s/updateParentRepo", self.updateParentRepo.__module__)
            logging.critical("Your data is corrupt!")
            logging.critical("Params: parentNode: %s, newRepoKey: %s" % (parentNode, newRepoKey))
            return

        def fixTxn(nodeKey, newRepoKey):
            node = db.Get(nodeKey)
            node["parentrepo"] = newRepoKey
            db.Put(node)

        # Fix all nodes
        q = db.Query(self.viewSkel("node").kindName).filter("parententry =", parentNode)
        for repo in q.iter():
            self.updateParentRepo(repo.key, newRepoKey, depth=depth + 1)
            db.RunInTransaction(fixTxn, repo.key, newRepoKey)

        # Fix the leafs on this level
        if self.leafSkelCls:
            q = db.Query(self.viewSkel("leaf").kindName).filter("parententry =", parentNode)
            for repo in q.iter():
                db.RunInTransaction(fixTxn, repo.key, newRepoKey)

    ## Internal exposed functions

    @internalExposed
    def pathToKey(self, key: db.Key):
        """
        Returns the recursively expanded path through the Tree from the root-node to a
        requested node.
        :param key: Key of the destination *node*.
        :returns: An nested dictionary with information about all nodes in the path from root to the requested node.
        """
        lastLevel = []
        for x in range(0, 99):
            currentNodeSkel = self.viewSkel("node")
            if not currentNodeSkel.fromDB(key):
                return []  # Either invalid key or listFilter prevented us from fetching anything
            if currentNodeSkel["parententry"] == currentNodeSkel["parentrepo"]:  # We reached the top level
                break
            levelQry = self.viewSkel("node").all().filter("parententry =", currentNodeSkel["parententry"])
            currentLevel = [{"skel": x,
                             "active": x["key"] == currentNodeSkel["key"],
                             "children": lastLevel if x["key"] == currentNodeSkel["key"] else []}
                            for x in self.listFilter(levelQry).fetch(99)]
            assert currentLevel, "Got emtpy parent list?"
            lastLevel = currentLevel
            key = currentNodeSkel["parententry"]
        return lastLevel

    ## External exposed functions

    @exposed
    def listRootNodes(self, *args, **kwargs) -> Any:
        """
        Renders a list of all available repositories for the current user using the
        modules default renderer.

        :returns: The rendered representation of the available root-nodes.
        """
        return self.render.listRootNodes(self.getAvailableRootNodes(*args, **kwargs))

    @exposed
    def list(self, skelType: SkelType, *args, **kwargs) -> Any:
        """
        Prepares and renders a list of entries.

        All supplied parameters are interpreted as filters for the elements displayed.

        Unlike other ViUR BasicApplications, the access control in this function is performed
        by calling the function :func:`listFilter`, which updates the query-filter to match only
        elements which the user is allowed to see.

        .. seealso:: :func:`listFilter`, :func:`viur.core.db.mergeExternalFilter`

        :returns: The rendered list objects for the matching entries.

        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """
        if not (skelType := self._checkSkelType(skelType)):
            raise errors.NotAcceptable(f"Invalid skelType provided.")
        skel = self.viewSkel(skelType)
        query = self.listFilter(skel.all().mergeExternalFilter(kwargs))  # Access control
        if query is None:
            raise errors.Unauthorized()
        res = query.fetch()
        return self.render.list(res)

    @exposed
    def structure(self, skelType: SkelType, *args, **kwargs) -> Any:
        """
        :returns: Returns the structure of our skeleton as used in list/view. Values are the defaultValues set
            in each bone.

        :raises: :exc:`viur.core.errors.NotAcceptable`, when an incorrect *skelType* is provided.
        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """
        if not (skelType := self._checkSkelType(skelType)):
            raise errors.NotAcceptable(f"Invalid skelType provided.")
        skel = self.viewSkel(skelType)
        if not self.canAdd(skelType, None):  # We can't use canView here as it would require passing a skeletonInstance.
            # As a fallback, we'll check if the user has the permissions to view at least one entry
            qry = self.listFilter(skel.all())
            if not qry or not qry.getEntry():
                raise errors.Unauthorized()
        return self.render.view(skel)

    @exposed
    def view(self, skelType: SkelType, key: str, *args, **kwargs) -> Any:
        """
        Prepares and renders a single entry for viewing.

        The entry is fetched by its *key* and its *skelType*.
        The function performs several access control checks on the requested entity before it is rendered.

        .. seealso:: :func:`canView`, :func:`onView`

        :returns: The rendered representation of the requested entity.

        :param skelType: May either be "node" or "leaf".
        :param key: URL-safe key of the parent.

        :raises: :exc:`viur.core.errors.NotAcceptable`, when an incorrect *skelType* is provided.
        :raises: :exc:`viur.core.errors.NotFound`, when no entry with the given *key* was found.
        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        """
        if not (skelType := self._checkSkelType(skelType)):
            raise errors.NotAcceptable(f"Invalid skelType provided.")
        skel = self.viewSkel(skelType)
        if not key:
            raise errors.NotAcceptable()
        # We return a single entry for viewing
        if not skel.fromDB(key):
            raise errors.NotFound()
        if not self.canView(skelType, skel):
            raise errors.Unauthorized()
        self.onView(skelType, skel)
        return self.render.view(skel)

    @exposed
    @forceSSL
    def add(self, skelType: SkelType, node: str, *args, **kwargs) -> Any:
        """
        Add a new entry with the given parent *node*, and render the entry, eventually with error notes
        on incorrect data. Data is taken by any other arguments in *kwargs*.

        The function performs several access control checks on the requested entity before it is added.

        .. seealso:: :func:`canAdd`, :func:`onAdd`, , :func:`onAdded`

        :param skelType: Defines the type of the new entry and may either be "node" or "leaf".
        :param node: URL-safe key of the parent.

        :returns: The rendered, added object of the entry, eventually with error hints.

        :raises: :exc:`viur.core.errors.NotAcceptable`, when no valid *skelType* was provided.
        :raises: :exc:`viur.core.errors.NotFound`, when no valid *node* was found.
        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        skey = kwargs.get("skey", "")

        if not (skelType := self._checkSkelType(skelType)):
            raise errors.NotAcceptable(f"Invalid skelType provided.")

        skel = self.addSkel(skelType)
        parentNodeSkel = self.editSkel("node")
        if not parentNodeSkel.fromDB(node):
            raise errors.NotFound("The provided parent node could not be found.")
        if not self.canAdd(skelType, parentNodeSkel):
            raise errors.Unauthorized()

        skel["parententry"] = parentNodeSkel["key"]
        # parentrepo may not exist in parentNodeSkel as it may be an rootNode
        skel["parentrepo"] = parentNodeSkel["parentrepo"] or parentNodeSkel["key"]

        if (len(kwargs) == 0  # no data supplied
            or not skel.fromClient(kwargs)  # failure on reading into the bones
            or not currentRequest.get().isPostRequest
            or ("bounce" in kwargs and kwargs["bounce"] == "1")  # review before adding
        ):
            return self.render.add(skel)
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()

        self.onAdd(skelType, skel)
        skel.toDB()
        self.onAdded(skelType, skel)
        return self.render.addSuccess(skel)

    @exposed
    @forceSSL
    def edit(self, skelType: SkelType, key: str, *args, **kwargs) -> Any:
        """
        Modify an existing entry, and render the entry, eventually with error notes on incorrect data.
        Data is taken by any other arguments in *kwargs*.

        The function performs several access control checks on the requested entity before it is added.

        .. seealso:: :func:`canEdit`, :func:`onEdit`, :func:`onEdited`

        :param skelType: Defines the type of the entry that should be modified and may either be "node" or "leaf".
        :param key: URL-safe key of the item to be edited.

        :returns: The rendered, modified object of the entry, eventually with error hints.

        :raises: :exc:`viur.core.errors.NotAcceptable`, when no valid *skelType* was provided.
        :raises: :exc:`viur.core.errors.NotFound`, when no valid *node* was found.
        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        skey = kwargs.get("skey", "")

        if not (skelType := self._checkSkelType(skelType)):
            raise errors.NotAcceptable(f"Invalid skelType provided.")

        skel = self.editSkel(skelType)
        if not skel.fromDB(key):
            raise errors.NotFound()
        if not self.canEdit(skelType, skel):
            raise errors.Unauthorized()
        if (len(kwargs) == 0  # no data supplied
            or not skel.fromClient(kwargs)  # failure on reading into the bones
            or not currentRequest.get().isPostRequest
            or ("bounce" in kwargs and kwargs["bounce"] == "1")  # review before adding
        ):
            return self.render.edit(skel)
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()
        self.onEdit(skelType, skel)
        skel.toDB()
        self.onEdited(skelType, skel)
        return self.render.editSuccess(skel)

    @exposed
    @forceSSL
    @forcePost
    def delete(self, skelType: SkelType, key: str, *args, **kwargs) -> Any:
        """
        Deletes an entry or an directory (including its contents).

        The function runs several access control checks on the data before it is deleted.

        .. seealso:: :func:`canDelete`, :func:`onDelete`, :func:`onDeleted`

        :param skelType: Defines the type of the entry that should be deleted and may either be "node" or "leaf".
        :param key: URL-safe key of the item to be deleted.

        :returns: The rendered, deleted object of the entry.

        :raises: :exc:`viur.core.errors.NotFound`, when no entry with the given *key* was found.
        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        skey = kwargs.get("skey", "")
        if not (skelType := self._checkSkelType(skelType)):
            raise errors.NotAcceptable(f"Invalid skelType provided.")
        skel = self.editSkel(skelType)
        if not skel.fromDB(key):
            raise errors.NotFound()
        if not self.canDelete(skelType, skel):
            raise errors.Unauthorized()
        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()
        if skelType == "node":
            self.deleteRecursive(skel["key"])
        self.onDelete(skelType, skel)
        skel.delete()
        self.onDeleted(skelType, skel)
        return self.render.deleteSuccess(skel, skelType=skelType)

    @CallDeferred
    def deleteRecursive(self, parentKey: str):
        """
        Recursively processes a delete request.

        This will delete all entries which are children of *nodeKey*, except *key* nodeKey.

        :param parentKey: URL-safe key of the node which children should be deleted.
        """
        nodeKey = db.keyHelper(parentKey, self.viewSkel("node").kindName)
        if self.leafSkelCls:
            for leaf in db.Query(self.viewSkel("leaf").kindName).filter("parententry =", nodeKey).iter():
                leafSkel = self.viewSkel("leaf")
                if not leafSkel.fromDB(leaf.key):
                    continue
                leafSkel.delete()
        for node in db.Query(self.viewSkel("node").kindName).filter("parententry =", nodeKey).iter():
            self.deleteRecursive(node.key)
            nodeSkel = self.viewSkel("node")
            if not nodeSkel.fromDB(node.key):
                continue
            nodeSkel.delete()

    @exposed
    @forceSSL
    @forcePost
    def move(self, skelType: SkelType, key: str, parentNode: str, *args, **kwargs) -> str:
        """
        Move a node (including its contents) or a leaf to another node.

        .. seealso:: :func:`canMove`

        :param skelType: Defines the type of the entry that should be moved and may either be "node" or "leaf".
        :param key: URL-safe key of the item to be moved.
        :param parentNode: URL-safe key of the destination node, which must be a node.

        :returns: The rendered, edited object of the entry.

        :raises: :exc:`viur.core.errors.NotFound`, when no entry with the given *key* was found.
        :raises: :exc:`viur.core.errors.Unauthorized`, if the current user does not have the required permissions.
        :raises: :exc:`viur.core.errors.PreconditionFailed`, if the *skey* could not be verified.
        """
        if not (skelType := self._checkSkelType(skelType)):
            raise errors.NotAcceptable(f"Invalid skelType provided.")

        skel = self.editSkel(skelType)  # srcSkel - the skeleton to be moved
        parentNodeSkel = self.baseSkel("node")  # destSkel - the node it should be moved into

        if not skel.fromDB(key):
            raise errors.NotFound("Cannot find key entity")

        if not parentNodeSkel.fromDB(parentNode):
            parentNode = utils.normalizeKey(db.Key.from_legacy_urlsafe(parentNode))

            if parentNode.kind != parentNodeSkel.kindName:
                raise errors.NotFound(
                    f"You provided a key of kind {parentNode.kind}, but require a {parentNodeSkel.kindName}."
                )

            raise errors.NotFound("Cannot find parentNode entity")

        if not self.canMove(skelType, skel, parentNodeSkel):
            raise errors.Unauthorized()

        if skel["key"] == parentNodeSkel["key"]:
            raise errors.NotAcceptable("Cannot move a node into itself")

        ## Test for recursion
        currLevel = db.Get(parentNodeSkel["key"])
        for _ in range(0, 99):
            if currLevel.key == skel["key"]:
                break
            if currLevel.get("rootNode"):
                # We reached a rootNode, so this is okay
                break
            currLevel = db.Get(currLevel["parententry"])
        else:  # We did not "break" - recursion-level exceeded or loop detected
            raise errors.NotAcceptable("Unable to find a root node in recursion?")

        # Test if we try to move a rootNode
        tmp = skel.dbEntity
        if "rootNode" in tmp and tmp["rootNode"] == 1:
            raise errors.NotAcceptable("Can't move a rootNode to somewhere else")

        if not securitykey.validate(kwargs.get("skey", ""), useSessionKey=True):
            raise errors.PreconditionFailed()

        currentParentRepo = skel["parentrepo"]
        skel["parententry"] = parentNodeSkel["key"]
        skel["parentrepo"] = parentNodeSkel["parentrepo"]  # Fixme: Need to recursive fixing to parentrepo?
        if "sortindex" in kwargs:
            try:
                skel["sortindex"] = float(kwargs["sortindex"])
            except:
                raise errors.PreconditionFailed()

        self.onEdit(skelType, skel)
        skel.toDB()
        self.onEdited(skelType, skel)

        # Ensure a changed parentRepo get's proagated
        if currentParentRepo != parentNodeSkel["parentrepo"]:
            self.updateParentRepo(key, parentNodeSkel["parentrepo"])

        return self.render.editSuccess(skel)

    ## Default access control functions

    def listFilter(self, query: db.Query) -> Optional[db.Query]:
        """
        Access control function on item listing.

        This function is invoked by the :func:`list` renderer and the related Jinja2 fetching function,
        and is used to modify the provided filter parameter to match only items that the current user
        is allowed to see.

        :param query: Query which should be altered.

        :returns: The altered filter, or None if access is not granted.
        """
        user = utils.getCurrentUser()
        if user and ("%s-view" % self.moduleName in user["access"] or "root" in user["access"]):
            return query
        return None

    def canView(self, skelType: SkelType, skel: SkeletonInstance) -> bool:
        """
        Checks if the current user can view the given entry.
        Should be identical to what's allowed by listFilter.
        By default, `meth:listFilter` is used to determine what's allowed and whats not; but this
        method can be overridden for performance improvements (to eliminate that additional database access).
        :param skel: The entry we check for
        :return: True if the current session is authorized to view that entry, False otherwise
        """
        queryObj = self.viewSkel(skelType).all().mergeExternalFilter({"key": skel["key"]})
        queryObj = self.listFilter(queryObj)  # Access control
        if queryObj is None:
            return False
        if not queryObj.getEntry():
            return False
        return True

    def canAdd(self, skelType: SkelType, parentNodeSkel: Optional[SkeletonInstance]) -> bool:
        """
        Access control function for adding permission.

        Checks if the current user has the permission to add a new entry.

        The default behavior is:
        - If no user is logged in, adding is generally refused.
        - If the user has "root" access, adding is generally allowed.
        - If the user has the modules "add" permission (module-add) enabled, adding is allowed.

        It should be overridden for a module-specific behavior.

        .. seealso:: :func:`add`

        :param skelType: Defines the type of the node that should be added.
        :param parentNodeSkel: The parent node where a new entry should be added.

        :returns: True, if adding entries is allowed, False otherwise.
        """
        user = utils.getCurrentUser()
        if not user:
            return False
        # root user is always allowed.
        if user["access"] and "root" in user["access"]:
            return True
        # user with add-permission is allowed.
        if user and user["access"] and "%s-add" % self.moduleName in user["access"]:
            return True
        return False

    def canEdit(self, skelType: SkelType, skel: SkeletonInstance) -> bool:
        """
        Access control function for modification permission.

        Checks if the current user has the permission to edit an entry.

        The default behavior is:
        - If no user is logged in, editing is generally refused.
        - If the user has "root" access, editing is generally allowed.
        - If the user has the modules "edit" permission (module-edit) enabled, editing is allowed.

        It should be overridden for a module-specific behavior.

        .. seealso:: :func:`edit`

        :param skelType: Defines the type of the node that should be edited.
        :param skel: The Skeleton that should be edited.

        :returns: True, if editing entries is allowed, False otherwise.
        """
        user = utils.getCurrentUser()
        if not user:
            return False
        if user["access"] and "root" in user["access"]:
            return True
        if user and user["access"] and "%s-edit" % self.moduleName in user["access"]:
            return True
        return False

    def canDelete(self, skelType: SkelType, skel: SkeletonInstance) -> bool:
        """
        Access control function for delete permission.

        Checks if the current user has the permission to delete an entry.

        The default behavior is:
        - If no user is logged in, deleting is generally refused.
        - If the user has "root" access, deleting is generally allowed.
        - If the user has the modules "deleting" permission (module-delete) enabled, \
         deleting is allowed.

        It should be overridden for a module-specific behavior.

        :param skelType: Defines the type of the node that should be deleted.
        :param skel: The Skeleton that should be deleted.

        .. seealso:: :func:`delete`

        :returns: True, if deleting entries is allowed, False otherwise.
        """
        user = utils.getCurrentUser()
        if not user:
            return False
        if user["access"] and "root" in user["access"]:
            return True
        if user and user["access"] and "%s-delete" % self.moduleName in user["access"]:
            return True
        return False

    def canMove(self, skelType: SkelType, node: SkeletonInstance, destNode: SkeletonInstance) -> bool:
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
        :param node: URL-safe key of the node to be moved.
        :param destNode: URL-safe key of the node where *node* should be moved to.

        .. seealso:: :func:`move`

        :returns: True, if deleting entries is allowed, False otherwise.
        """
        user = utils.getCurrentUser()
        if not user:
            return False
        if user["access"] and "root" in user["access"]:
            return True
        if user and user["access"] and "%s-edit" % self.moduleName in user["access"]:
            return True
        return False

    ## Overridable eventhooks

    def onAdd(self, skelType: SkelType, skel: SkeletonInstance):
        """
        Hook function that is called before adding an entry.

        It can be overridden for a module-specific behavior.

        :param skelType: Defines the type of the node that shall be added.
        :param skel: The Skeleton that is going to be added.

        .. seealso:: :func:`add`, :func:`onAdded`
        """
        pass

    def onAdded(self, skelType: SkelType, skel: SkeletonInstance):
        """
        Hook function that is called after adding an entry.

        It should be overridden for a module-specific behavior.
        The default is writing a log entry.

        :param skelType: Defines the type of the node that has been added.
        :param skel: The Skeleton that has been added.

        .. seealso:: :func:`add`, :func:`onAdd`
        """
        logging.info("Entry of kind %r added: %s", skelType, skel["key"])
        flushCache(kind=skel.kindName)
        user = utils.getCurrentUser()
        if user:
            logging.info("User: %s (%s)" % (user["name"], user["key"]))

    def onEdit(self, skelType: SkelType, skel: SkeletonInstance):
        """
        Hook function that is called before editing an entry.

        It can be overridden for a module-specific behavior.

        :param skelType: Defines the type of the node that shall be edited.
        :param skel: The Skeleton that is going to be edited.

        .. seealso:: :func:`edit`, :func:`onEdited`
        """
        pass

    def onEdited(self, skelType: SkelType, skel: SkeletonInstance):
        """
        Hook function that is called after modifying an entry.

        It should be overridden for a module-specific behavior.
        The default is writing a log entry.

        :param skelType: Defines the type of the node that has been edited.
        :param skel: The Skeleton that has been modified.

        .. seealso:: :func:`edit`, :func:`onEdit`
        """
        logging.info("Entry of kind %r changed: %s", skelType, skel["key"])
        flushCache(key=skel["key"])
        user = utils.getCurrentUser()
        if user:
            logging.info("User: %s (%s)" % (user["name"], user["key"]))

    def onView(self, skelType: SkelType, skel: SkeletonInstance):
        """
        Hook function that is called when viewing an entry.

        It should be overridden for a module-specific behavior.
        The default is doing nothing.

        :param skelType: Defines the type of the node that is viewed.
        :param skel: The Skeleton that is viewed.

        .. seealso:: :func:`view`
        """
        pass

    def onDelete(self, skelType: SkelType, skel: SkeletonInstance):
        """
        Hook function that is called before deleting an entry.

        It can be overridden for a module-specific behavior.

        :param skelType: Defines the type of the node that shall be deleted.
        :param skel: The Skeleton that is going to be deleted.

        .. seealso:: :func:`delete`, :func:`onDeleted`
        """
        pass

    def onDeleted(self, skelType: SkelType, skel: SkeletonInstance):
        """
        Hook function that is called after deleting an entry.

        It should be overridden for a module-specific behavior.
        The default is writing a log entry.

        ..warning: Saving the skeleton again will undo the deletion
        (if the skeleton was a leaf or a node with no children).

        :param skelType: Defines the type of the node that is deleted.
        :param skel: The Skeleton that has been deleted.

        .. seealso:: :func:`delete`, :func:`onDelete`
        """
        logging.info("Entry deleted: %s (%s)" % (skel["key"], type(skel)))
        flushCache(key=skel["key"])
        user = utils.getCurrentUser()
        if user:
            logging.info("User: %s (%s)" % (user["name"], user["key"]))


Tree.vi = True
Tree.admin = True
