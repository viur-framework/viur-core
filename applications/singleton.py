# -*- coding: utf-8 -*-
from server.bones import baseBone
from server.skeleton import Skeleton, skeletonByKind
from server import utils, session,  errors, conf, securitykey, exposed, forceSSL
from google.appengine.api import users
from google.appengine.ext import db
import logging

class Singleton( object ):
	"""
	Singleton is a ViUR BasicApplication.

	It is used to store one single data entity, and needs to be sub-classed for individual modules.

	:ivar kindName: Name of the kind of data entity that are managed by the application. \
	This information is used to bind a specific :class:`server.skeleton.Skeleton`-class to the \
	application. For more information, refer to the function :func:`_resolveSkel`.
	:vartype kindName: str

	:ivar adminInfo: todo short info on how to use adminInfo.
	:vartype adminInfo: dict | callable
	"""

	kindName = None
	def adminInfo(self):
		return {
			"name": self.__class__.__name__,        # Module name as shown in the admin tools
		"handler": "singleton",                 # Which handler to invoke
		"icon": "icons/modules/singleton.svg",  # Icon for this module
		}

				
	def getKey(self):
		"""
		Returns the DB-Key for the current context.

		This implementation provides one module-global key.
		It *must* return *exactly one* key at any given time in any given context.

		:returns: Current context DB-key
		:rtype: str
		"""
		return( "%s-modulkey" % self.editSkel().kindName )

	def __init__( self, modulName, modulPath, *args, **kwargs ):
		self.modulName = modulName
		self.modulPath = modulPath

		if self.adminInfo:
			for r in ["edit", "view"]:
				rightName = "%s-%s" % ( modulName, r )

				if not rightName in conf["viur.accessRights"]:
					conf["viur.accessRights"].append( rightName )

	def _resolveSkel(self, *args, **kwargs):
		"""
		Retrieve the generally associated :class:`server.skeleton.Skeleton` that is used by
		the application.

		This is either be defined by the member variable *kindName* or by a Skeleton named like the
		application class in lower-case order.

		If this behavior is not wanted, it can be definitely overridden by defining module-specific
		:func:`viewSkel`,:func:`addSkel`, or :func:`editSkel` functions, or by overriding this
		function in general.

		:return: Returns a Skeleton instance that matches the application.
		:rtype: server.skeleton.Skeleton
		"""

		if self.kindName:
			kName = self.kindName
		else:
			kName = unicode( type(self).__name__ ).lower()

		return skeletonByKind( kName )()

	def viewSkel( self, *args, **kwargs ):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for viewing the existing entry.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`addSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for viewing the singleton entry.
		:rtype: server.skeleton.Skeleton
		"""
		return self._resolveSkel(*args, **kwargs)

	def editSkel( self, *args, **kwargs ):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for editing the existing entry.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for editing the entry.
		:rtype: server.skeleton.Skeleton
		"""
		return self._resolveSkel(*args, **kwargs)

## External exposed functions

	@exposed
	def preview( self, skey, *args, **kwargs ):
		"""
		Renders data for the entry, without reading it from the database.
		This function allows to preview the entry without writing it to the database.

		Any entity values are provided via *kwargs*.

		The function uses the viewTemplate of the application.

		:returns: The rendered representation of the supplied data.
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
		Prepares and renders the singleton entry for viewing.

		The function performs several access control checks on the requested entity before it is rendered.

		.. seealso:: :func:`viewSkel`, :func:`canView`, :func:`onItemViewed`

		:returns: The rendered representation of the entity.

		:raises: :exc:`server.errors.NotFound`, if there is no singleton entry existing, yet.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		"""

		skel = self.viewSkel()
		if not self.canView( ):
			raise errors.Unauthorized()

		id = str( db.Key.from_path( self.editSkel().kindName, self.getKey() ) )

		if not skel.fromDB( id ):
			raise errors.NotFound()

		self.onItemViewed( skel )
		return self.render.view( skel )

	@exposed
	@forceSSL
	def edit( self, *args, **kwargs ):
		"""
		Modify the existing entry, and render the entry, eventually with error notes on incorrect data.

		The entry is fetched by its entity key, which either is provided via *kwargs["id"]*,
		or as the first parameter in *args*. The function performs several access control checks
		on the singleton's entity before it is modified.

		.. seealso:: :func:`editSkel`, :func:`onItemEdited`, :func:`canEdit`

		:returns: The rendered, edited object of the entry, eventually with error hints.

		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""

		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""

		skel = self.editSkel()

		if not self.canEdit( ):
			raise errors.Unauthorized()

		id = db.Key.from_path( self.editSkel().kindName, self.getKey() )

		if not skel.fromDB( str(id) ): #Its not there yet; we need to set the key again
			skel.setValues( {}, key=id )

		if (len(kwargs) == 0 # no data supplied
		    or skey == "" #no skey provided
			or not skel.fromClient( kwargs ) # failure on reading into the bones
			or ("bounce" in kwargs.keys() and kwargs["bounce"] == "1")): # review before changing
			return self.render.edit( skel )

		if not securitykey.validate( skey, acceptSessionKey=True ):
			raise errors.PreconditionFailed()

		skel.toDB( )
		self.onItemEdited( skel )
		return self.render.editItemSuccess( skel )

	@exposed
	@forceSSL
	def amend(self, *args, **kwargs):
		"""
		Amend is like the standard lists edit action, but it only amends the values coming from outside.
		The supplied data must not be complete nor contain all required fields.
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		skel = self.editSkel()

		id = db.Key.from_path( self.editSkel().kindName, self.getKey() )
		if not skel.fromDB( id ):
			raise errors.NotAcceptable()
		if not self.canEdit( ):
			raise errors.Unauthorized()

		if (len(kwargs) == 0 or skey == "" ):
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

		logging.info("skey is:"+skey)
		if not securitykey.validate( skey, acceptSessionKey=True ):
			logging.info("validation failed...")
			raise errors.PreconditionFailed()
			pass

		skel.toDB()
		self.onItemEdited( skel )
		return self.render.editItemSuccess( skel )

	def getContents( self ):
		"""
		Returns the entity of this singleton application as :class:`server.skeleton.Skeleton` object.

		:returns: The content as Skeleton provided by :func:`viewSkel`.
		"""
		skel = self.viewSkel()
		id = str( db.Key.from_path( self.viewSkel().kindName, self.getKey() ) )

		if not skel.fromDB( id ):
			return None

		return skel

	def canPreview( self ):
		"""
		Access control function for preview permission.

		Checks if the current user has the permission to preview the singletons entry.

		The default behavior is:
		- If no user is logged in, previewing is generally refused.
		- If the user has "root" access, previewing is generally allowed.
		- If the user has the modules "edit" permission (module-edit) enabled, \
		previewing is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`preview`

		:returns: True, if previewing entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()

		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user["access"] and "%s-edit" % self.viewSkel.kindName in user["access"]:
			return True

		return False

	def canEdit( self ):
		"""
		Access control function for modification permission.

		Checks if the current user has the permission to edit the singletons entry.

		The default behavior is:
		- If no user is logged in, editing is generally refused.
		- If the user has "root" access, editing is generally allowed.
		- If the user has the modules "edit" permission (module-edit) enabled, editing is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`edit`

		:returns: True, if editing is allowed, False otherwise.
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

	def canView(self):
		"""
		Access control function for viewing permission.

		Checks if the current user has the permission to view the singletons entry.

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
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user["access"] and "%s-view" % self.modulName in user["access"]:
			return( True )
		return( False )

	def onItemEdited( self, skel ):
		"""
		Hook function that is called after modifying the entry.

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

Singleton.admin=True
Singleton.jinja2=True
Singleton.vi=True
