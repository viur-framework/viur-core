# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server import session, errors, conf
from server.applications.tree import Tree, TreeSkel
from server.bones import *
from server import utils
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext import ndb
import json, urlparse
from server.tasks import PeriodicTask
import json
from google.appengine.api.images import get_serving_url
from quopri import decodestring
import email.header
from base64 import b64decode
from google.appengine.ext import deferred
import logging


def findPathInRootNode( rootNode, path):
	dbObj = utils.generateExpandoClass( "file_rootNode" )
	repo = ndb.Key( urlsafe=rootNode ).get()
	for comp in path.split("/"):
		if not repo:
			return( None )
		if not comp:
			continue
		repo = dbObj.query().filter( ndb.GenericProperty("parentdir") == str( repo.key.urlsafe() ) )\
				.filter( ndb.GenericProperty("name") == comp).get()
	if not repo:
		return( None )
	else:
		return( repo )
		
class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
	# http://code.google.com/p/googleappengine/issues/detail?id=2749
	# Open since Sept. 2010, claimed to be fixed in Version 1.7.2 (September 18, 2012)
	# and still totally broken
	def decodeFileName(self, name):
		try:
			if name.startswith("=?"): #RFC 2047
				return( unicode( email.Header.make_header( email.Header.decode_header(name+"\n") ) ) )
			elif "=" in name and not name.endswith("="): #Quoted Printable
				return( decodestring( name.encode("ascii") ).decode("UTF-8") )
			else: #Maybe base64 encoded
				return( b64decode( name.encode("ascii") ).decode("UTF-8") )
		except: #Sorry - I cant guess whats happend here
			return( name )
			
	def post(self):
		try:
			session.current.load( self.request.cookies )
			res = []
			dbObj = utils.generateExpandoClass( "file" )
			if "rootNode" in self.request.arguments() and self.request.get("rootNode") and "path" in self.request.arguments():
				if not conf["viur.mainApp"].file.canUploadTo( self.request.get("rootNode"), self.request.get("path") ):
					for upload in self.get_uploads():
						upload.delete()
					return
				# The file is uploaded into a rootNode
				repo = findPathInRootNode( self.request.get("rootNode"), self.request.get("path") )
				if not repo:
					for upload in self.get_uploads():
						upload.delete()
				else:
					for upload in self.get_uploads():
						filename = self.decodeFileName( upload.filename )
						#Check if a file with this name already exists in this directory
						oldFile = utils.generateExpandoClass( "file" ).query()\
								.filter( ndb.GenericProperty("parentdir") == str(repo.key.urlsafe()))\
								.filter( ndb.GenericProperty("name") == filename ).get()
						if oldFile: # Delete the old one (=>Overwrite this file)
							utils.markFileForDeletion( oldFile.dlkey )
							oldFile.key.delete()
						if str( upload.content_type ).startswith("image/"):
							try:
								servingURL = get_serving_url( upload.key() )
							except:
								servingURL = ""
						else:
							servingURL = ""
						fileObj = dbObj(	name= filename,
										name_idx= filename.lower(), 
										size=upload.size,
										meta_mime=upload.content_type,
										dlkey=str(upload.key()),
										parentdir=str(repo.key.urlsafe()),
										parentrepo=self.request.get("rootNode"), 
										servingurl=servingURL, 
										weak = False
									)
						fileObj.put()
					#Fixme(): Bad things will happen if uploaded from Webbrowser
					res.append( { "name": filename,
								"size":float( upload.size ),
								"meta_mime":str(upload.content_type),
								"dlkey":str(upload.key()),
								"parentdir":str( repo.key.urlsafe() ) } )
			else:
				#We got a anonymous upload (a file not registered in any rootNode yet)
				if not conf["viur.mainApp"].file.canUploadTo( None, None ):
					for upload in self.get_uploads():
						upload.delete()
					return
				for upload in self.get_uploads():
					filename = self.decodeFileName( upload.filename )
					if str( upload.content_type ).startswith("image/"):
						servingURL = get_serving_url( upload.key() )
					else:
						servingURL = ""
					fileObj = dbObj(	name= filename,
									size=upload.size,
									meta_mime=upload.content_type,
									dlkey=str(upload.key()),
									servingurl=servingURL, 
									weak=True #Ensure this entry vanishes
									)
					res.append( { "name":filename,
								"size":float( upload.size ),
								"meta_mime":str(upload.content_type),
								"dlkey":str(upload.key()), 
								"id": str(fileObj.put().urlsafe()) } )
			for r in res:
				logging.info("Got a successfull upload: %s (%s)" % (r["name"], r["dlkey"] ) )
			user = utils.getCurrentUser()
			if user:
				logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
			self.response.write( json.dumps( res ) )
		except Exception as e: #Something got wrong - delete all uploads
			logging.error( e )
			for upload in self.get_uploads():
				upload.delete()
		

class DownloadHandler(blobstore_handlers.BlobstoreDownloadHandler):
	def get(self, dlkey, fileName="file.dat", *args, **kwargs ):
		dlkey = urlparse.unquote( dlkey )
		if "/" in dlkey:
			try:
				dlkey, fileName = dlkey.split("/")
			except ValueError: #There are too much /
				self.error(404)
		if "download" in kwargs and kwargs["download"]=="1":
			fname = "".join( [ c for c in fileName if c in string.ascii_lowercase+string.ascii_uppercase + string.digits+[".","-","_"] ] )
			self.response.headers.add_header( "Content-disposition", "attachment; filename=%s" % ( fname ) )
		if not blobstore.get(dlkey):
			self.error(404)
		else:
			self.send_blob(dlkey)

	def post(self, dlkey, fileName="file.dat", *args, **kwargs ):
		return( self.get( dlkey, fileName, *args, **kwargs ) )


class fileBaseSkel( TreeSkel ):
	entityName = "file"
	size = stringBone( descr="Size", params={"searchable": True,  "frontend_list_visible": True}, readonly=True )
	dlkey = stringBone( descr="Download-Key", params={"searchable": True,  "frontend_list_visible": True}, readonly=True )
	name = stringBone( descr="Filename", params={"searchable": True,  "frontend_list_visible": True}, readonly=True, caseSensitive=False )
	meta_mime = stringBone( descr="Mime-Info", params={"searchable": True,  "frontend_list_visible": True}, readonly=True )
	#testData = stringBone( descr="TestData", params={"searchable": True,  "frontend_list_visible": True} )
	
class File( Tree ):
	viewSkel = fileBaseSkel
	editSkel = fileBaseSkel
	
	maxuploadsize = None
	uploadHandler = []
	
	rootNodes = {"personal":"my files"}
	adminInfo = {"name": "my files", #Name of this modul, as shown in Apex (will be translated at runtime)
				"handler": "tree.file",  #Which handler to invoke
				"icon": "icons/modules/folder.png", #Icon for this modul
				}

	def getUploadURL( self, *args, **kwargs ):
		return( blobstore.create_upload_url('/file/upload') )
	getUploadURL.exposed=True


	def getAvailableRootNodes( self, name ):
		thisuser = utils.getCurrentUser()
		if thisuser:
			repo = self.ensureOwnUserRootNode()
			res = [ { "name":_("Meine Datein"), "key": str(repo.key.urlsafe()) } ]
			if "root" in thisuser["access"]:
				"""Add at least some repos from other users"""
				dbObj = utils.generateExpandoClass( self.viewSkel.entityName+"_rootNode" )
				userObj = utils.generateExpandoClass( "user" )
				repos = dbObj.query().filter( ndb.GenericProperty("type") == "user").fetch(100)
				for repo in repos:
					if not "user" in repo.dynamic_properties():
						continue
					user = userObj.all().filter("uid =", repo.user).get()
					if not user or not "name" in user.dynamic_properties():
						continue
					res.append( { "name":user.name, "key": str(repo.key.urlsafe()) } )
			return( res )
		return( [] )
	getAvailableRootNodes.internalExposed=True


	def view( self, dlkey, filename="file.dat", *args, **kwargs ):
		assert False #This should never be reached
	view.exposed = True
	
	def add( self, *args, **kwargs ):
		raise errors.NotAcceptable()
	add.exposed = True

	def delete( self, rootNode, path, name, type ):
		"""Our timestamp-based update approach dosnt work here, so we'll do another trick"""
		repo = self.findPathInRootNode( rootNode, path )
		if not self.canDelete( repo, name, type ):
			raise errors.Unauthorized()
		if not repo:
			raise errors.PreconditionFailed()
		if type=="entry":
			fileEntry = utils.generateExpandoClass( self.viewSkel.entityName ).query()\
				.filter( ndb.GenericProperty("parentdir") == str(repo.key.urlsafe()) )\
				.filter( ndb.GenericProperty("name") == name).get() 
			if fileEntry:
				utils.markFileForDeletion( fileEntry.dlkey )
				fileEntry.key.delete()
		else:
			delRepo = utils.generateExpandoClass( self.viewSkel.entityName+"_rootNode" ).query()\
				.filter( ndb.GenericProperty("parentdir") == str(repo.key.urlsafe()) )\
				.filter( ndb.GenericProperty("name") == name).get() 
			if delRepo:
				deferred.defer( self.deleteDirsRecursive, str(delRepo.key.urlsafe()) )
				delRepo.key.delete()
		self.onItemDeleted( rootNode, path, name, type )
		return( self.render.deleteSuccess() )
	delete.exposed=True

	def deleteDirsRecursive( self, parentKey ):
		fileClass = utils.generateExpandoClass( self.viewSkel.entityName )
		dirClass = utils.generateExpandoClass( self.viewSkel.entityName+"_rootNode" )
		files = fileClass.query().filter( ndb.GenericProperty("parentdir") == parentKey  ).iter()
		for fileEntry in files:
			utils.markFileForDeletion( fileEntry.dlkey )
			fileEntry.key.delete()
		dirs = dirClass.query().filter( ndb.GenericProperty("parentdir") == parentKey ).iter()
		for d in dirs:
			deferred.defer( self.deleteDirsRecursive, str(d.key.urlsafe()) )
			d.key.delete()

	def canViewRootNode( self, repo ):
		user = utils.getCurrentUser()
		return( self.isOwnUserRootNode( repo ) or (user and "root" in user["access"]) )

	def canMkDir( self, repo, dirname ):
		return( self.isOwnUserRootNode( repo.key.urlsafe() ) )
		
	def canRename( self, repo, src, dest ):
		return( self.isOwnUserRootNode( repo.key.urlsafe() ) )

	def canCopy( self, srcRepo, destRepo, type, deleteold ):
		return( self.isOwnUserRootNode( srcRepo.key.urlsafe() ) and self.isOwnUserRootNode( destRepo.key.urlsafe() ) )
		
	def canDelete( self, repo, name, type ):
		return( self.isOwnUserRootNode( repo.key.urlsafe() ) )

	def canEdit( self, id ):
		user = utils.getCurrentUser()
		return( user and "root" in user["access"] )
	
	def canUploadTo( self, rootNode, path ):
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if not thisuser:
			return(False)
		if not rootNode:
			return( True )
		key = ndb.Key( self.viewSkel.entityName+"_rootNode", "rep_user_%s" % str( thisuser["id"] ) ).urlsafe()
		if str( rootNode ) == key:
			return( True )
		return( False )
		
File.json=True
File.jinja2=True

@PeriodicTask( 60*60*4 )
def cleanup( ):
	maxIterCount = 2 #How often a file will be checked for deletion
	expurgeClass = utils.generateExpandoClass( "viur-deleted-files" )
	fileClass = utils.generateExpandoClass( "file" )
	for file in expurgeClass.query().iter():
		if not "dlkey" in file._properties.keys():
			file.key.delete()
		elif fileClass.query().filter(  ndb.GenericProperty("dlkey") == file.dlkey ).filter( ndb.GenericProperty("weak") == False ).get():
			file.key.delete()
		else:
			if file.itercount > maxIterCount:
				blobstore.delete( file.dlkey )
				file.key.delete()
				for f in fileClass.query().filter( ndb.GenericProperty("dlkey") == file.dlkey).fetch(1000,  keys_only=True): #There should be exactly 1 or 0 of these
					f.key.delete()
			else:
				file.itercount = file.itercount+1
				file.put()
