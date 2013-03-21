# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server import session, errors, conf
from server.applications.tree import Tree, TreeSkel
from server.bones import *
from server import utils, db
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
import json, urlparse
from server.tasks import PeriodicTask
import json
import os
from google.appengine.api.images import get_serving_url
from quopri import decodestring
import email.header
from base64 import b64decode
from google.appengine.ext import deferred
import logging


def findPathInRootNode( rootNode, path):
	repo = db.Get( rootNode )
	for comp in path.split("/"):
		if not repo:
			return( None )
		if not comp:
			continue
		repo = db.Query( "file_rootNode" ).filter( "parentdir =", str( repo.key() ) )\
				.filter( "name =", comp).get()
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
		self.internalRequest = False
		self.isDevServer = "Development" in os.environ['SERVER_SOFTWARE'] #Were running on development Server
		self.isSSLConnection = self.request.host_url.lower().startswith("https://") #We have an encrypted channel
		try:
			session.current.load( self )
			res = []
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
						oldFile = db.Query( "file" ).filter( "parentdir =", str(repo.key())).filter( "name =", filename ).get()
						if oldFile: # Delete the old one (=>Overwrite this file)
							utils.markFileForDeletion( oldFile["dlkey"] )
							db.Delete( oldFile.key() )
						if str( upload.content_type ).startswith("image/"):
							try:
								servingURL = get_serving_url( upload.key() )
							except:
								servingURL = ""
						else:
							servingURL = ""
						fileObj = db.Entity(	"file" )
						fileObj[ "name" ]= filename
						fileObj[ "name_idx" ] = filename.lower()
						fileObj[ "size" ]=upload.size
						fileObj[ "meta_mime" ]=upload.content_type
						fileObj[ "dlkey" ]=str(upload.key())
						fileObj[ "parentdir" ]=str(repo.key())
						fileObj[ "parentrepo" ]=self.request.get("rootNode")
						fileObj[ "servingurl" ]=servingURL
						fileObj[ "weak" ] = False
						db.Put( fileObj )
					#Fixme(): Bad things will happen if uploaded from Webbrowser
					res.append( { "name": filename,
								"size":float( upload.size ),
								"meta_mime":str(upload.content_type),
								"dlkey":str(upload.key()),
								"parentdir":str( repo.key() ) } )
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
					fileObj = db.Entity(	"file", 
									name= filename,
									size=upload.size,
									meta_mime=upload.content_type,
									dlkey=str(upload.key()),
									servingurl=servingURL, 
									weak=True #Ensure this entry vanishes
									)
					db.Put( fileObj )
					res.append( { "name":filename,
								"size":float( upload.size ),
								"meta_mime":str(upload.content_type),
								"dlkey":str(upload.key()), 
								"id": str(fileObj.key()) } )
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
	kindName = "file"
	size = stringBone( descr="Size", params={"indexed": True,  "frontend_list_visible": True}, readOnly=True )
	dlkey = stringBone( descr="Download-Key", params={"indexed": True,  "frontend_list_visible": True}, readOnly=True, indexed=True )
	name = stringBone( descr="Filename", params={"indexed": True,  "frontend_list_visible": True}, readOnly=True, caseSensitive=False, indexed=True )
	meta_mime = stringBone( descr="Mime-Info", params={"indexed": True,  "frontend_list_visible": True}, readOnly=True )
	#testData = stringBone( descr="TestData", params={"indexed": True,  "frontend_list_visible": True} )
	
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
		logging.error( thisuser )
		if thisuser:
			repo = self.ensureOwnUserRootNode()
			res = [ { "name":_("Meine Datein"), "key": str(repo.key()) } ]
			if "root" in thisuser["access"]:
				"""Add at least some repos from other users"""
				repos = db.Query( self.viewSkel.kindName+"_rootNode" ).filter( "type =", "user").run(100)
				for repo in repos:
					if not "user" in repo.keys():
						continue
					user = db.Query( "user" ).filter("uid =", repo.user).get()
					if not user or not "name" in user.keys():
						continue
					res.append( { "name":user["name"], "key": str(repo.key()) } )
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
			fileEntry = db.Query( self.viewSkel.kindName )\
				.filter( "parentdir =",  str(repo.key()) )\
				.filter( "name =", name).get() 
			if fileEntry:
				utils.markFileForDeletion( fileEntry["dlkey"] )
				db.Delete( fileEntry.key() )
		else:
			delRepo = db.Query( self.viewSkel.kindName+"_rootNode" )\
				.filter( "parentdir = ", str(repo.key()) )\
				.filter( "name", name).get()
			if delRepo:
				deferred.defer( self.deleteDirsRecursive, str(delRepo.key()) )
				db.Delete( delRepo.key() )
		self.onItemDeleted( rootNode, path, name, type )
		return( self.render.deleteSuccess() )
	delete.exposed=True

	def deleteDirsRecursive( self, parentKey ):
		files = db.Query( self.viewSkel().kindName ).filter( "parentdir =", parentKey  ).run()
		for fileEntry in files:
			utils.markFileForDeletion( fileEntry["dlkey"] )
			db.Delete( fileEntry.key() )
		dirs = db.Query( self.viewSkel.kindName+"_rootNode" ).filter( "parentdir", parentKey ).run()
		for d in dirs:
			deferred.defer( self.deleteDirsRecursive, str(d.key()) )
			db.Delete( d.key() )

	def canViewRootNode( self, repo ):
		user = utils.getCurrentUser()
		return( self.isOwnUserRootNode( repo ) or (user and "root" in user["access"]) )

	def canMkDir( self, repo, dirname ):
		return( self.isOwnUserRootNode( str(repo.key() ) ) )
		
	def canRename( self, repo, src, dest ):
		return( self.isOwnUserRootNode( str(repo.key() ) ) )

	def canCopy( self, srcRepo, destRepo, type, deleteold ):
		return( self.isOwnUserRootNode( str( srcRepo.key() ) ) and self.isOwnUserRootNode( str( destRepo.key() ) ) )
		
	def canDelete( self, repo, name, type ):
		return( self.isOwnUserRootNode( str( repo.key() ) ) )

	def canEdit( self, id ):
		user = utils.getCurrentUser()
		return( user and "root" in user["access"] )
	
	def canUploadTo( self, rootNode, path ):
		thisuser = conf["viur.mainApp"].user.getCurrentUser()
		if not thisuser:
			return(False)
		if not rootNode:
			return( True )
		key = str( db.Key.from_path( self.viewSkel.kindName+"_rootNode", "rep_user_%s" % str( thisuser["id"] ) ) )
		if str( rootNode ) == key:
			return( True )
		return( False )
		
File.json=True
File.jinja2=True

@PeriodicTask( 60*4 )
def cleanup( ):
	maxIterCount = 2 #How often a file will be checked for deletion
	for file in db.Query( "viur-deleted-files" ).iter():
		if not "dlkey" in file.keys():
			db.Delete( file.key() )
		elif db.Query( "file" ).filter( "dlkey =", file["dlkey"] ).filter( "weak =", False ).get():
			db.Delete( file.key() )
		else:
			if file["itercount"] > maxIterCount:
				blobstore.delete( file["dlkey"] )
				db.Delete( file.key() )
				for f in db.Query( "file").filter( "dlkey =", file["dlkey"]).iter( keysOnly=True ): #There should be exactly 1 or 0 of these
					db.Delete( f )
			else:
				file["itercount"] += 1
				db.Put( file )
