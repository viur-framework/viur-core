# -*- coding: utf-8 -*-
from server import utils, session, errors, conf, securitykey, request
from server import forcePost, forceSSL, exposed, internalExposed

from server.applications import BasicApplication

import logging

class List(BasicApplication):
	"""
	List is a ViUR BasicApplication.

	It is used for multiple data entities of the same kind, and needs to be sub-classed for individual
	modules.

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
			"handler": "list",                      # Which handler to invoke
			"icon": "icons/modules/list.svg"        # Icon for this module
		}

	def __init__( self, modulName, modulPath, *args, **kwargs ):
		super(List, self).__init__(modulName, modulPath, *args, **kwargs)

	def viewSkel( self, *args, **kwargs ):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for viewing an existing entry from the list.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`addSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for viewing an entry.
		:rtype: server.skeleton.Skeleton
		"""
		return self._resolveSkel(*args, **kwargs)

	def addSkel( self, *args, **kwargs ):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for adding an entry to the list.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for adding an entry.
		:rtype: server.skeleton.Skeleton
		"""
		return self._resolveSkel(*args, **kwargs)

	def editSkel( self, *args, **kwargs ):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for editing an existing entry from the list.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for editing an entry.
		:rtype: server.skeleton.Skeleton
		"""
		return self._resolveSkel(*args, **kwargs)

## External exposed functions

	@exposed
	@forcePost
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

		if not securitykey.validate( skey ):
			raise errors.PreconditionFailed()

		skel = self.viewSkel()
		skel.fromClient( kwargs )

		return self.render.view( skel )


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

		if "canView" in dir( self ):
			if not skel.fromDB( id ):
				raise errors.NotFound()

			if not self.canView( skel ):
				raise errors.Unauthorized()

		else:
			queryObj = self.viewSkel().all().mergeExternalFilter( {"id":  id} )
			queryObj = self.listFilter( queryObj ) #Access control

			if queryObj is None:
				raise errors.Unauthorized()

			skel = queryObj.getSkel()
			if not skel:
				raise errors.NotFound()

		self.onItemViewed( skel )
		return self.render.view( skel )

	@exposed
	def list( self, *args, **kwargs ):
		"""
		Prepares and renders a list of entries.

		All supplied parameters are interpreted as filters for the elements displayed.

		Unlike other ViUR BasicApplications, the access control in this function is performed
		by calling the function :func:`listFilter`, which updates the query-filter to match only
		elements which the user is allowed to see.

		.. seealso:: :func:`listFilter`, :func:`server.db.mergeExternalFilter`

		:returns: The rendered list objects for the matching entries.

		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		"""
		query = self.listFilter( self.viewSkel().all().mergeExternalFilter( kwargs ) ) #Access control
		if query is None:
			raise errors.Unauthorized()

		return self.render.list( query.fetch() )

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

		if not self.canEdit( skel ):
			raise errors.Unauthorized()

		if (len(kwargs) == 0 # no data supplied
			or skey == "" # no security key
			or not request.current.get().isPostRequest # failure if not using POST-method
			or not skel.fromClient(kwargs) # failure on reading into the bones
			or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1") # review before changing
	        ):

			# render the skeleton in the version it could as far as it could be read.
			return self.render.edit( skel )

		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		skel.toDB() # write it!
		self.onItemEdited( skel )

		return self.render.editItemSuccess( skel )

	"""
	@exposed
	@forceSSL
	def amend(self, *args, **kwargs):
		" ""
		Amend is like the standard lists edit action, but it only amends the values coming from outside.
		The supplied data must not be complete nor contain all required fields.
		" ""
		logging.error(kwargs)
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

		if not skel.fromDB( id ):
			raise errors.NotAcceptable()

		if not self.canEdit( skel ):
			raise errors.Unauthorized()

		if (len(kwargs) == 0
			or skey == ""
			or not request.current.get().isPostRequest ):
			return self.render.edit( skel )

		count = 0
		for k in kwargs.keys():
			# Check for valid bones
			if k in [ "id" ] or not k in skel.keys():
				continue

			# Check for correct data fetch
			if (skel[k].fromClient(k, kwargs)
			    and skel[k].required
				and not kwargs[k]):

				logging.info("XX %s = %s" % (k,kwargs[k]))
				count += 1
			else:
				logging.info("OK %s = %s" % (k,kwargs[k]))

		if count:
			return self.render.edit( skel )

		if not securitykey.validate( skey, acceptSessionKey=True ):
			#raise errors.PreconditionFailed()
			pass

		skel.toDB()
		self.onItemEdited( skel )
		return self.render.editItemSuccess( skel )
	"""

	@forceSSL
	@exposed
	def add( self, *args, **kwargs ):
		"""
		Add a new entry, and render the entry, eventually with error notes on incorrect data.
		Data is taken by any other arguments in *kwargs*.

		The function performs several access control checks on the requested entity before it is added.

		.. seealso:: :func:`addSkel`, :func:`onItemAdded`, :func:`canAdd`

		:returns: The rendered, added object of the entry, eventually with error hints.

		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""

		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""

		if not self.canAdd():
			raise errors.Unauthorized()

		skel = self.addSkel()

		if (len(kwargs) == 0 # no data supplied
			or skey == "" # no skey supplied
	        or not request.current.get().isPostRequest # failure if not using POST-method
	        or not skel.fromClient( kwargs ) # failure on reading into the bones
	        or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1") # review before adding
	        ):
			# render the skeleton in the version it could as far as it could be read.
			return self.render.add( skel )

		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		skel.toDB()
		self.onItemAdded( skel )

		return self.render.addItemSuccess( skel )

	@forceSSL
	@forcePost
	@exposed
	def delete( self, id, skey, *args, **kwargs ):
		"""
		Delete an entry.

		The function runs several access control checks on the data before it is deleted.

		.. seealso:: :func:`canDelete`, :func:`editSkel`, :func:`onItemDeleted`

		:returns: The rendered, deleted object of the entry.

		:raises: :exc:`server.errors.NotFound`, when no entry with the given *id* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""

		skel = self.editSkel()
		if not skel.fromDB( id ):
			raise errors.NotFound()

		if not self.canDelete( skel ):
			raise errors.Unauthorized()

		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		skel.delete( )
		self.onItemDeleted( skel )

		return self.render.deleteSuccess( skel )


## Default access control functions

	def listFilter( self, filter ):
		"""
		Access control function on item listing.

		This function is invoked by the :func:`list` renderer and the related Jinja2 fetching function,
		and is used to modify the provided filter parameter to match only items that the current user
		is allowed to see.

		:param filter: Query which should be altered.
		:type filter: :class:`server.db.Query`

		:returns: The altered filter, or None if access is not granted.
		:type filter: :class:`server.db.Query`
		"""
		user = utils.getCurrentUser()

		if user and ("%s-view" % self.modulName in user["access"] or "root" in user["access"] ):
			return filter

		return None


	def canAdd( self ):
		"""
		Access control function for adding permission.

		Checks if the current user has the permission to add a new entry.

		The default behavior is:
		- If no user is logged in, adding is generally refused.
		- If the user has "root" access, adding is generally allowed.
		- If the user has the modules "add" permission (module-add) enabled, adding is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`add`

		:returns: True, if adding entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		# root user is always allowed.
		if user["access"] and "root" in user["access"]:
			return True

		# user with add-permission is allowed.
		if user and user["access"] and "%s-add" % self.modulName in user["access"]:
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

		if (user and user["access"]
	        and ("%s-add" % self.modulName in user["access"]
	                or "%s-edit" % self.modulName in user["access"])):
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

		if user and user["access"] and "%s-edit" % self.modulName in user["access"]:
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

		if user and user["access"] and "%s-delete" % self.modulName in user["access"]:
			return True

		return False


## Override-able event-hooks

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


List.admin = True
List.jinja2 = True
List.vi = True
