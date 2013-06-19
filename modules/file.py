# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server import session, errors, conf, request
from server.applications.tree import Tree, TreeNodeSkel, TreeLeafSkel
from server import forcePost, forceSSL, exposed, internalExposed
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
import collections
import logging
import cgi



class fileBaseSkel( TreeNodeSkel ):
	kindName = "file"
	size = stringBone( descr="Size", params={"indexed": True, "frontend_list_visible": True}, readOnly=True, indexed=True, searchable=True )
	dlkey = stringBone( descr="Download-Key", params={"frontend_list_visible": True}, readOnly=True, indexed=True )
	name = stringBone( descr="Filename", params={"frontend_list_visible": True}, caseSensitive=False, indexed=True, searchable=True )
	meta_mime = stringBone( descr="Mime-Info", params={"frontend_list_visible": True}, readOnly=True, indexed=True, )
	weak = booleanBone( descr="Is a weak Reference?", indexed=True, readOnly=True, visible=False )


class fileNodeSkel( TreeLeafSkel ):
	kindName = "file_rootNode"
	name = stringBone( descr="Name", required=True, indexed=True, searchable=True )

class File( Tree ):
	viewLeafSkel = fileBaseSkel
	editLeafSkel = fileBaseSkel
	addLeafSkel = fileBaseSkel
	
	viewNodeSkel = fileNodeSkel
	editNodeSkel = fileNodeSkel
	addNodeSkel = fileNodeSkel
	
	maxuploadsize = None
	uploadHandler = []
	
	rootNodes = {"personal":"my files"}
	adminInfo = {	"name": "my files", #Name of this modul, as shown in Admin (will be translated at runtime)
			"handler": "tree.simple.file",  #Which handler to invoke
			"icon": "icons/modules/folder.png", #Icon for this modul
			}

	def getUploads(self, field_name=None):
		"""
			Get uploads sent to this handler.
			Cheeky borrowed from blobstore_handlers.py - © 2007 Google Inc.

			Args:
				field_name: Only select uploads that were sent as a specific field.

			Returns:
				A list of BlobInfo records corresponding to each upload.
				Empty list if there are no blob-info records for field_name.
			
		"""
		uploads = collections.defaultdict(list)
		for key, value in request.current.get().request.params.items():
			if isinstance(value, cgi.FieldStorage):
				if 'blob-key' in value.type_options:
					uploads[key].append(blobstore.parse_blob_info(value))
		if field_name:
			return list(uploads.get(field_name, []))
		else:
			results = []
			for uploads in uploads.itervalues():
				results.extend(uploads)
			return results

	def getUploadURL( self, *args, **kwargs ):
		return( blobstore.create_upload_url( "%s/upload" % self.modulPath ) )
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

	
	@exposed
	def upload( self, node=None, *args, **kwargs ):
		try:
			canAdd = self.canAdd( node, "leaf" )
		except:
			canAdd = False
		if not canAdd:
			for upload in self.get_uploads():
				upload.delete()
			raise errors.Forbidden()
		if 1:
			res = []
			if node:
				# The file is uploaded into a rootNode
				nodeSkel = self.editNodeSkel()
				if not nodeSkel.fromDB( node ):
					for upload in self.getUploads():
						upload.delete()
				else:
					for upload in self.getUploads():
						fileName = upload.filename
						if str( upload.content_type ).startswith("image/"):
							try:
								servingURL = get_serving_url( upload.key() )
							except:
								servingURL = ""
						else:
							servingURL = ""
						fileSkel = self.addLeafSkel()
						fileSkel.setValues( {	"name": fileName,
									"size": upload.size,
									"meta_mime": upload.content_type,
									"dlkey": str(upload.key()),
									"servingurl": servingURL,
									"parentdir": str(node),
									"parentrepo": nodeSkel.parentrepo.value,
									"weak": False } )
						fileSkel.toDB()
						res.append( fileSkel )
			else:
				#We got a anonymous upload (a file not registered in any rootNode yet)
				for upload in self.get_uploads():
					filename = upload.filename
					if str( upload.content_type ).startswith("image/"):
						try:
							servingURL = get_serving_url( upload.key() )
						except:
							servingURL = ""
					else:
						servingURL = ""

					fileSkel = self.addLeafSkel()
					fileSkel.setValues( {	"name": fileName,
								"size": upload.size,
								"meta_mime": upload.content_type,
								"dlkey": str(upload.key()),
								"servingurl": servingURL,
								"parentdir": None,
								"parentrepo": None,
								"weak": True } )
					fileSkel.toDB()
					res.append( fileSkel )
			for r in res:
				logging.info("Got a successfull upload: %s (%s)" % (r.name.value, r.dlkey.value ) )
			user = utils.getCurrentUser()
			if user:
				logging.info("User: %s (%s)" % (user["name"], user["id"] ) )
			logging.error( self.render )
			logging.error( self.render.add )
			logging.error( res )
			return( self.render.addItemSuccess( res ) )
			#self.response.write( json.dumps( res ) )

	@exposed
	def download( self, blobKey, fileName="", download="", *args, **kwargs ):
		if download == "1":
			fname = "".join( [ c for c in fileName if c in string.ascii_lowercase+string.ascii_uppercase + string.digits+[".","-","_"] ] )
			request.current.get().response.headers.add_header( "Content-disposition", "attachment; filename=%s" % ( fname ) )
		info = blobstore.get(blobKey)
		if not info:
			raise errors.NotFound()
		request.current.get().response.clear()
		request.current.get().response.headers['Content-Type'] = str(info.content_type)
		request.current.get().response.headers[blobstore.BLOB_KEY_HEADER] = str(blobKey)
		return("")
		
	@exposed
	def view( self, *args, **kwargs ):
		try:
			return( super(File, self).view( *args, **kwargs ) )
		except (errors.NotFound, errors.NotAcceptable) as e:
			if len(args)>0 and blobstore.get( args[0] ):
				raise( errors.Redirect( "%s/download/%s" % (self.modulPath, args[0]) ) )
			elif len(args)>1 and blobstore.get( args[1] ):
				raise( errors.Redirect( "%s/download/%s" % (self.modulPath, args[1]) ) )
			raise( e )

	@exposed
	@forceSSL
	@forcePost
	def add( self, skelType, node, *args, **kwargs ):
		if skelType != "node": #We can't add files directly (they need to be uploaded
			raise errors.NotAcceptable()
		return( super( File, self ).add( skelType, node, *args, **kwargs ) )

	@exposed
	@forceSSL
	@forcePost
	def delete( self, skelType, id  ):
		"""Our timestamp-based update approach dosnt work here, so we'll do another trick"""
		if skelType=="node":
			skel = self.editNodeSkel
		elif skelType=="leaf":
			skel = self.editLeafSkel
		else:
			assert False
		repo = skel()
		if not repo.fromDB( id ):
			raise errors.NotFound()
		if not self.canDelete( repo, skelType ):
			raise errors.Unauthorized()
		if skelType=="leaf":
			utils.markFileForDeletion( repo.dlkey.value )
			repo.delete( id )
		else:
			deferred.defer( self.deleteDirsRecursive, str(id) )
			repo.delete( id )
		self.onItemDeleted( repo )
		return( self.render.deleteSuccess( repo ) )
	delete.exposed=True

	def deleteDirsRecursive( self, parentKey ):
		files = db.Query( self.editLeafSkel().kindName ).filter( "parentdir =", parentKey  ).run()
		for fileEntry in files:
			import logging
			logging.error( fileEntry )
			utils.markFileForDeletion( fileEntry["dlkey"] )
			db.Delete( fileEntry.key() )
		dirs = db.Query( self.editNodeSkel().kindName ).filter( "parentdir", parentKey ).run()
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
		
	def canDelete( self, skel, skelType ):
		user = utils.getCurrentUser()
		if user and "root" in user["access"]:
			return( True )
		return( self.isOwnUserRootNode( str( skel.id.value ) ) )

	def canEdit( self, skel ):
		user = utils.getCurrentUser()
		return( user and "root" in user["access"] )
	
		
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
