# -*- coding: utf-8 -*-
from server.bones import baseBone, numericBone
from server.skeleton import Skeleton
from server import utils
from server import errors, session, conf
from server import db
from time import time
from google.appengine.api import users
from datetime import datetime
import logging

class TreeSkel( Skeleton ):
	parentdir = baseBone( descr="Parent", visible=False, indexed=True, readOnly=True )
	parentrepo = baseBone( descr="BaseRepo", visible=False, indexed=True, readOnly=True )


class Tree( object ):
	""" 
		This application holds hierarchy data.
		In this application, entries are sorted in directories, which can be nested.
	"""
	adminInfo = {	"name": "TreeApplication", #Name of this modul, as shown in Apex (will be translated at runtime)
				"handler": "tree",  #Which handler to invoke
				"icon": "", #Icon for this modul
				#,"orderby":"changedate",
				#"orderdir":1
				}
	viewSkel = TreeSkel

	def __init__( self, modulName, modulPath, *args, **kwargs ):
		self.modulName = modulName
		self.modulPath = modulPath
		if self.adminInfo and self.editSkel:
			rights = ["add", "edit", "view", "delete"]
			for r in rights:
				rightName = "%s-%s" % (modulName, r )
				if not rightName in conf["viur.accessRights"]:
					conf["viur.accessRights"].append( rightName )

	def jinjaEnv(self, env ):
		"""
			Provide some additional Functions to the template
		"""
		env.globals["updatePath"] = self.updatePath
		env.globals["canAdd"] = self.canAdd
		env.globals["canPreview"] = self.canPreview
		env.globals["canDelete"] = self.canDelete
		env.globals["canView"] = self.canView
		env.globals["canList"] = self.canList
		env.globals["canEdit"] = self.canEdit
		env.globals["canCopy"] = self.canCopy
		env.globals["canRename"] = self.canRename
		env.globals["canMkDir"] = self.canMkDir
		return( env )
	
	def updatePath( self, path=None, action=None ):
		"""
			Allows manipulation of a given Path from Templates
			@param path: Path to manipulate
			@type path: String
			@action: Strings: Append a segment; List: Append all elements of this list; Int: Positive: Limit the path to the first n segments; Negative: Remove the last n Elements
			@returns: The new path as string
		"""
		if not path:
			reqParams = request.current.get().kwargs
			if not "path" in reqParams.keys():
				return("/")
			path = reqParams["path"]
		path = [ x for x in path.split("/") if x ]
		if isinstance( action, int ): #Remove the last n elements
			try:
				path = path[ : action ]
			except IndexError:
				pass
		elif isinstance( action, basestring ): #Append this one element
			path.append( action )
		elif isinstance( action, list ): #Append all elements
			path += action
		return( "/"+("/".join( path ) ) )

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

	def findPathInRootNode( self, rootNode, path ):
		"""
			Fetches the subnode specified by path in the rootNode.
			@param rootNode: Urlsafe-key of the rootNode
			@type rootNode: String
			@param path: Path to traverse
			@type path: String
			@returns: The Node-object (as ndb.Expando) or None, if the path was invalid
		"""
		repo = db.Get( rootNode )
		for comp in path.split("/"):
			if not repo:
				return( None )
			if not comp:
				continue
			repo = db.Query( self.viewSkel.kindName+"_rootNode" ).filter( "parentdir =", str( repo.key() ) ).filter( "name =", comp).get()
		if not repo:
			return( None )
		else:
			return( repo )
			
	def ensureOwnUserRootNode( self ):
		"""
			Ensures, that an rootNode for the current user exists
			@returns: The Node-object (as ndb.Expando) or None, if this was request was made by a guest
		"""
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if thisuser:
			key = "rep_user_%s" % str( thisuser["id"] )
			return( db.GetOrInsert( key, self.viewSkel.kindName+"_rootNode", creationdate=datetime.now(), rootNode=1, user=str( thisuser["id"] ) ) )

	def ensureOwnModulRootNode( self ):
		"""
			Ensures that the modul-global rootNode exists.
			@returns: The Node-object (as ndb.Expando)
		"""
		key = "rep_modul_repo"
		return( db.GetOrInsert( key, self.viewSkel.kindName+"_rootNode", creationdate=datetime.now(), rootNode=1 ) )

	def getRootNode(self, subRepo):
		"""
			Returns the root-rootNode for a given (sub)-repo
			@param subRepo: RootNode-Key
			@type subRepo: String
			@returns: db.Expando
		"""
		repo = db.Get( subRepo )
		seenList = [str( repo.key()) ] #Prevent infinite Loops if something goes realy wrong
		while "parentdir" in repo.keys():
			repo = db.Get( repo["parentdir"] )
			assert repo and not str( repo.key() ) in seenList
			seenList.append( str( repo.key() ) )
		return( repo )

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
		repo = self.getRootNode(  repo )
		user_repo = self.ensureOwnUserRootNode()
		if str( repo.key() ) == str(user_repo.key()):
			return( True )
		return( False )

	def listRootNodes(self, name=None ):
		"""
			Renders a list of all available repositories for the current user
		"""
		return( self.render.listRootNodes( self.getAvailableRootNodes( name ) ) )
	listRootNodes.exposed=True
	
	def mkDir(self, rootNode,  path, dirname, *args, **kwargs):
		"""
			Creates a new directory in the given rootNode under the given path.
			@param rootNode: Urlsafe-Key of the rootNode
			@type rootNode: String
			@param path: Path under which the directory will be created
			@type path: String
			@param dirname: Name of the new directory
			@type dirname: String
		"""
		repo = self.findPathInRootNode( rootNode, path )
		if not self.canMkDir( repo, dirname ):
			raise errors.Unauthorized()
		if not repo or "/" in dirname:
			raise errors.PreconditionFailed()
		dbObj = db.Entity( self.viewSkel.kindName+"_rootNode" )
		dbObj[ "name" ] = dirname
		dbObj[ "parentdir" ] = str(repo.key() )
		db.Put( dbObj )
		return( self.render.addDirSuccess( rootNode,  path, dirname ) )
	mkDir.exposed = True
	mkDir.forceSSL = True
	
	def rename(self,  rootNode, path, src, dest ):
		"""
			Renames an Entry or Directory
			@param rootNode: Urlsafe-Key of the rootNode
			@type rootNode: String
			@param path: Path of the entry/directory
			@type path: String
			@param src: Old name of the entry/directory
			@type src: String
			@param dest: New name of the entry/directory
			@type dest: String
		"""
		repo = self.findPathInRootNode( rootNode, path )
		if not self.canRename( repo, src, dest ):
			raise errors.Unauthorized()
		if not repo:
			raise errors.PreconditionFailed()
		fileRepoObj = db.Query( self.viewSkel().kindName+"_rootNode" )\
					.filter( "parentdir =", str(repo.key()))\
					.filter( "name", src).get()
		if fileRepoObj: #Check if we rename a Directory
			fileRepoObj["name"] = dest
			db.Put( fileRepoObj )
		else: #we rename a File
			fileObj = db.Query( self.viewSkel().kindName )\
					.filter( "parentdir =", str(repo.key()))\
					.filter( "name", src).get()
			if fileObj:
				fileObj["name"] = dest
				db.Put( fileObj )
		return self.render.renameSuccess( rootNode, path, src, dest )
	rename.exposed = True
	rename.forceSSL = True

	def copy( self, srcrepo, srcpath, name, destrepo, destpath, type, deleteold="0" ):
		"""
			Copy or move an entry, or a directory (including its contents).
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
		srcRepo = self.findPathInRootNode( srcrepo, srcpath )
		destRepo = self.findPathInRootNode( destrepo, destpath )
		if not self.canCopy( srcRepo, destRepo, type, deleteold ):
			raise errors.Unauthorized()
		if not all( [srcRepo, destRepo] ):
			raise errors.PreconditionFailed()
		if type=="entry":
			srcFileObj = db.Query( self.viewSkel().kindName ).filter( "parentdir =", str(srcRepo.key())).filter( "name =", name).get()
			if srcFileObj:
				destFileObj = db.Entity( self.viewSkel().kindName )
				for key in srcFileObj.keys():
					destFileObj[ key ] =  srcFileObj[ key ]
				destFileObj["parentdir"] = str( destRepo.key() )
				db.Put( destFileObj )
				if( deleteold=="1" ): # *COPY* an *DIRECTORY*
					db.Delete( srcFileObj.key() )
		else:
			newRepo = db.Entity( self.viewSkel.kindName+"_rootNode" )
			newRepo[ "parentdir" ] = str(destRepo.key() )
			newRepo[ "name" ] = name
			db.Put( newRepo )
			fromRepo = db.Query( self.viewSkel().kindName+"_rootNode").filter( "parentdir =", str(srcRepo.key())).filter( "name",  name).get()
			assert fromRepo
			self.cloneDirecotyRecursive( fromRepo, newRepo )
			if deleteold=="1":
				self.deleteDirsRecursive( fromRepo.key() )
				db.Delete( fromRepo.key() )
		return( self.render.copySuccess( srcrepo, srcpath, name, destrepo, destpath, type, deleteold ) )
	copy.exposed = True
	copy.forceSSL = True
	
	def cloneDirecotyRecursive( self, srcRepo, destRepo ):
		"""
			Recursivly processes an copy/move request
		"""
		entityTypeFile = self.viewSkel().kindName
		entityTypeDir = entityTypeFile+"_rootNode"
		subDirs = db.Query( entityTypeDir ).filter( "parentdir =", str(srcRepo.key())).run(100)
		subFiles = db.Query( entityTypeFile ).filter( "parentdir", str(srcRepo.key())).run(100)
		destRootRepo = self.getRootNode( str(destRepo.key() ) )
		for subDir in subDirs:
			newSubdir = db.Entity( entityTypeDir )
			newSubdir[ "parentdir" ] = str(destRepo.key())
			newSubdir[ "name" ] = subDir["name"]
			db.Put( newSubdir )
			self.cloneDirecotyRecursive( subDir, newSubdir )
		for subFile in subFiles:
			newFile = db.Entity( entityTypeFile )
			for k, v in subFile.items():
				newFile[ k ] = v
			newFile[ "parentdir" ] = str( destRepo.key() )
			newFile[ "parentrepo" ] = str( destRootRepo.key() )
			db.Put( newFile )

	def delete( self, rootNode, path, name, type ):
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
		repo = self.findPathInRootNode( rootNode, path )
		if not self.canDelete( repo, name, type ):
			raise errors.Unauthorized()
		if not repo:
			raise errors.PreconditionFailed()
		if type=="entry":
			fileEntry = db.Query( self.viewSkel().kindName ).filter( "parentdir =", str(repo.key() ) ).filter( "name =", name).get() 
			if fileEntry:
				skel = self.viewSkel()
				skel.delete( str( fileEntry.key() ) )
		else:
			delRepo = db.Query( self.viewSkel.kindName+"_rootNode" ).filter( "parentdir =", str(repo.key() ) ).filter( "name =", name).get() 
			if delRepo:
				self.deleteDirsRecursive( delRepo )
				db.Delete( delRepo.key() )
		self.onItemDeleted( rootNode, path, name, type )
		return( self.render.deleteSuccess( rootNode, path, name, type ) )
	delete.exposed = True
	delete.forceSSL = True

	def deleteDirsRecursive( self, repo ):
		"""
			Recursivly processes an delete request
		"""
		files = db.Query( self.viewSkel().kindName ).filter( "parentdir", str(repo.key()) ).run()
		skel = self.viewSkel()
		for f in files:
			skel.delete( str( f.key() ) )
		dirs = db.Query( self.viewSkel().kindName+"_rootNode" ).filter( "parentdir", str(repo.key()) ).run()
		for d in dirs:
			self.deleteDirsRecursive( d )
		db.Delete( [x.key() for x in dirs ] )

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
	
	def list( self, rootNode, path, *args, **kwargs ):
		"""
			List the entries and directorys of the given rootNode under the given path
			@param rootNode: Urlsafe-key of the rootNode
			@type rootNode: String
			@param path: Path to the level which should be displayed
			@type path: String
		"""
		repo = self.findPathInRootNode( rootNode, path )
		if not repo or not self.canList( repo, rootNode, path ):
			raise errors.Unauthorized()
		subdirs = []
		for entry in db.Query( self.viewSkel().kindName+"_rootNode" ).filter( "parentdir =", str(repo.key()) ).run( 100 ):
			subdirs.append( entry[ "name" ] )
		if not path and kwargs: #Were searching for a particular entry
			subdirs = [] #Dont list any directorys here
			newArgs = kwargs.copy()
			newArgs["parentrepo"] = str(repo.key())
			#queryObj = db.Query(utils.buildDBFilter( self.viewSkel(), newArgs )
			entrys = self.viewSkel().all().filter( newArgs ).fetch( 100 )
		else:
			#queryObj = utils.buildDBFilter( self.viewSkel(), {"parentdir": str(repo.key.urlsafe())} )
			entrys = self.viewSkel().all().filter( "parentdir =", str(repo.key()) ).fetch( 100 )
		return( self.render.listRootNodeContents( subdirs, entrys, rootNode=rootNode, path=path ) )
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
		if not self.canEdit( id ):
			raise errors.Unauthorized()
		if not skel.fromDB( id ):
			raise errors.NotAcceptable()
		if len(kwargs)==0 or skey=="" or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.edit( skel ) )
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		skel.toDB( id )
		self.onItemEdited( id, skel )
		return self.render.editItemSuccess( skel )
	edit.exposed = True
	edit.forceSSL = True

	def add( self, rootNode, path, *args, **kwargs ):
		"""
			Add a new entry in the given rootNode and path.
			@param rootNode: Urlsafe-key of the rootNode
			@type rootNode: String
			@param path: Path to the level in which the entry should be added
			@type path: String
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		repo = self.findPathInRootNode( rootNode, path )
		if not repo:
			raise errors.Unauthorized()
		
		if not self.canAdd( ):
			raise errors.Unauthorized()
		skel = self.addSkel()
		if not skel.fromClient( kwargs ) or len(kwargs)==0 or skey=="" or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.add( skel ) )
		skel.parentdir.value = str( repo.key() )
		skel.parentrepo.value = rootNode
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		id = skel.toDB( )
		self.onItemAdded( id, skel )
		return self.render.addItemSuccess( id, skel )
	add.exposed = True
	add.forceSSL = True
	
	def canAdd( self ):
		"""
			Checks if the current user has the right to add a new entry
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
	
	def canDelete( self, repo, name, type ):
		"""
			Checks if the current user has the right to delete an directory/entry
			@param repo: Subnode from which the element will be removed
			@type repo: ndb.Expando
			@param name: Name of the element, which will be removed
			@type name: String
			@param type: "entry" if an entry should be removed, otherwise its tried to remove an directory
			@type type: String
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
	
	def canView(self, id ):
		"""
			Checks if the current user has the right view the given entry.
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

	def canList( self, repo, parentRepoKey, path ):
		"""
			Checks if the current user has the right list the contents of the given level in the given rootNode.
			Note: repo is the sub-node derived from parentRepoKey and path
			@param repo: Subnode from which will be displayed
			@type repo: ndb.Expando
			@param parentRepoKey: Urlsafe-key of the root-node of this rootNode
			@type parentRepoKey: String
			@param path: Path from the root-node.
			@type path: String
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		logging.error( user )
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user["access"] and "%s-view" % self.modulName in user["access"]:
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
	
	def canCopy( self, srcRepo, destRepo, type, deleteOld ):
		"""
			Checks if the current user can copy or move entries from srcRepo to destRepo
			@param srcRepo: Subnode from which will be copied/moved
			@type srcRepo: ndb.Expando
			@param destRepo: Subnode to which will be copied/moved
			@type destRepo: ndb.Expando
			@param type: "entry" if an entry should be removed, otherwise its tried to remove an directory
			@type type: String
			@param deleteOld: "1" means move, everything else copy
			@type deleteOld: String
			@returns: True, if hes allowed to do so, False otherwise.
		"""
		user = utils.getCurrentUser()
		if not user:
			return( False )
		if user["access"] and "root" in user["access"]:
			return( True )
		if user["access"] and "%s-edit" % self.modulName in user["access"] and "%s-add" % self.modulName in user["access"] :
			return( True )
		return( False )
	
	def canRename( self, repo, src, dest ):
		"""
			Checks if the current user can rename an entry/directory in the given rootNode
			@param repo: Subnode where the element will be renamed
			@type repo: ndb.Expando
			@param src: Old name
			@type src: String
			@param dest: New name
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
	
	def canMkDir( self, repo, dirname ):
		"""
			Checks if the current user is allowed to create a new directory inside the given node.
			@param repo: Subnode where the directory will be created
			@type repo: ndb.Expando
			@param dirname: New directory name
			@type dirname: String
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
	
	def onItemDeleted( self, rootNode, path, name, type): #Fixme: Fix Docstring
		"""
			Hook. Can be overriden to hook the onItemDeleted-Event
			Note: Saving the skeleton again will undo the deletion.
		"""
		logging.info("Entry deleted: %s%s" % ( path, name ) )
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["id"] ) )

Tree.admin = True
Tree.jinja2 = True
Tree.ops = True
