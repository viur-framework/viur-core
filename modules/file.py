# -*- coding: utf-8 -*-

from server import utils, db, securitykey, session, errors, conf, request, forcePost, forceSSL, exposed, internalExposed
from server.skeleton import Skeleton, skeletonByKind
from server.bones import *
from server.prototypes.tree import Tree, TreeNodeSkel, TreeLeafSkel
from server.tasks import callDeferred, PeriodicTask
from datetime import datetime, timedelta
from urlparse import urlparse
from quopri import decodestring
from base64 import urlsafe_b64decode
from hashlib import sha256
from google.appengine.ext import blobstore
from google.appengine.api import images
import email.header
import collections, logging, cgi, string

class fileBaseSkel(TreeLeafSkel):
	"""
		Default file leaf skeleton.
	"""
	kindName = "file"

	size = stringBone(descr="Size", readOnly=True, indexed=True, searchable=True)
	dlkey = stringBone(descr="Download-Key", readOnly=True, indexed=True)
	name = stringBone(descr="Filename", caseSensitive=False, indexed=True, searchable=True)
	metamime = stringBone(descr="Mime-Info", readOnly=True, indexed=True, visible=False)
	meta_mime = stringBone(descr="Mime-Info", readOnly=True, indexed=True, visible=False)
	mimetype = stringBone(descr="Mime-Info", readOnly=True, indexed=True )
	weak = booleanBone(descr="Weak reference", indexed=True, readOnly=True, visible=False)
	servingurl = stringBone(descr="Serving URL", readOnly=True)
	width = numericBone(descr="Width", indexed=True, readOnly=True, searchable=True)
	height = numericBone(descr="Height", indexed=True, readOnly=True, searchable=True)

	def refresh(self):
		# Update from blobimportmap
		try:
			oldKeyHash = sha256(self["dlkey"]).hexdigest().encode("hex")
			res = db.Get( db.Key.from_path("viur-blobimportmap", oldKeyHash))
		except:
			res = None
		if res and res["oldkey"] == self["dlkey"]:
			self["dlkey"] = res["newkey"]
			self["servingurl"] = res["servingurl"]
			logging.info("Refreshing file dlkey %s (%s)" % (self["dlkey"], self["servingurl"]))
		else:
			if self["servingurl"]:
				try:
					self["servingurl"] = images.get_serving_url(self["dlkey"])
				except Exception as e:
					logging.exception(e)

		super(fileBaseSkel, self).refresh()

	def preProcessBlobLocks(self, locks):
		"""
			Ensure that our dlkey is locked even if we don't have a filebone here
		"""
		locks.add(self["dlkey"])
		return locks

	def fromDB(self, *args, **kwargs):
		r = super(fileBaseSkel, self).fromDB(*args, **kwargs)
		if not self["mimetype"]:
			if self["meta_mime"]:
				self["mimetype"] = self["meta_mime"]
			elif self["metamime"]:
				self["mimetype"] = self["metamime"]
		return r

	def setValues(self, values):
		r = super(fileBaseSkel, self).setValues(values)
		if not self["mimetype"]:
			if self["meta_mime"]:
				self["mimetype"] = self["meta_mime"]
			elif self["metamime"]:
				self["mimetype"] = self["metamime"]
		return r


class fileNodeSkel(TreeNodeSkel):
	"""
		Default file node skeleton.
	"""
	kindName = "file_rootNode"
	name = stringBone(descr="Name", required=True, indexed=True, searchable=True)


class File(Tree):

	viewLeafSkel = fileBaseSkel
	editLeafSkel = fileBaseSkel
	addLeafSkel = fileBaseSkel

	viewNodeSkel = fileNodeSkel
	editNodeSkel = fileNodeSkel
	addNodeSkel = fileNodeSkel

	maxuploadsize = None
	uploadHandler = []

	adminInfo = {
		"name": "File",
		"handler": "tree.simple.file",
		"icon": "icons/modules/my_files.svg"
	}

	blobCacheTime = 60*60*24  # Requests to file/download will be served with cache-control: public, max-age=blobCacheTime if set

	def decodeFileName(self, name):
		# http://code.google.com/p/googleappengine/issues/detail?id=2749
		# Open since Sept. 2010, claimed to be fixed in Version 1.7.2 (September 18, 2012)
		# and still totally broken
		try:
			if name.startswith("=?"): #RFC 2047
				return unicode( email.Header.make_header(email.Header.decode_header(name + "\n")))
			elif "=" in name and not name.endswith("="): #Quoted Printable
				return decodestring(name.encode("ascii")).decode("UTF-8")
			else: #Maybe base64 encoded
				return urlsafe_b64decode(name.encode("ascii")).decode("UTF-8")
		except: #Sorry - I cant guess whats happend here
			if isinstance(name, str) and not isinstance(name, unicode):
				try:
					return name.decode("UTF-8", "ignore")
				except:
					pass

			return name

	def getUploads(self, field_name = None):
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
				if "blob-key" in value.type_options:
					uploads[key].append(blobstore.parse_blob_info(value))
		if field_name:
			return list(uploads.get(field_name, []))
		results = []
		for uploads in uploads.itervalues():
			results.extend(uploads)
		return results


	@callDeferred
	def deleteRecursive(self, parentKey):
		files = db.Query( self.editLeafSkel().kindName ).filter("parentdir =", parentKey).iter()
		for fileEntry in files:
			utils.markFileForDeletion(fileEntry["dlkey"])
			skel = self.editLeafSkel()

			if skel.fromDB(str(fileEntry.key())):
				skel.delete()
		dirs = db.Query(self.editNodeSkel().kindName).filter("parentdir", parentKey).iter(keysOnly=True)
		for d in dirs:
			self.deleteRecursive(str(d))
			skel = self.editNodeSkel()
			if skel.fromDB(str(d)):
				skel.delete()

	@exposed
	def getUploadURL( self, *args, **kwargs ):
		skey = kwargs.get("skey", "")
		if not self.canAdd("leaf", None):
			raise errors.Forbidden()
		if not securitykey.validate(skey):
			raise errors.PreconditionFailed()
		return blobstore.create_upload_url("%s/upload" % self.modulePath)

	@internalExposed
	def getAvailableRootNodes(self, name, *args, **kwargs):
		thisuser = utils.getCurrentUser()
		if not thisuser:
			return []
		repo = self.ensureOwnUserRootNode()
		res = [{
			"name": _("My Files"),
			"key": str(repo.key())
		}]
		if "root" in thisuser["access"]:
			# Add at least some repos from other users
			repos = db.Query(self.viewNodeSkel.kindName + "_rootNode").filter("type =", "user").run(100)
			for repo in repos:
				if not "user" in repo:
					continue
				user = db.Query( "user" ).filter("uid =", repo.user).get()
				if not user or not "name" in user:
					continue
				res.append({
					"name": user["name"],
					"key": str(repo.key())
				})
		return res

	@exposed
	def upload( self, node=None, *args, **kwargs ):
		try:
			canAdd = self.canAdd("leaf", node)
		except:
			canAdd = False
		if not canAdd:
			for upload in self.getUploads():
				upload.delete()
			raise errors.Forbidden()
		try:
			res = []
			if node:
				# The file is uploaded into a rootNode
				nodeSkel = self.editNodeSkel()
				if not nodeSkel.fromDB(node):
					for upload in self.getUploads():
						upload.delete()
					raise errors.NotFound()
				else:
					weak = False
					parentDir = str(node)
					parentRepo =  nodeSkel["parentrepo"]
			else:
				weak = True
				parentDir = None
				parentRepo = None
			# Handle the actual uploads
			for upload in self.getUploads():
				fileName = self.decodeFileName(upload.filename)
				if str(upload.content_type).startswith("image/"):
					try:
						servingURL = images.get_serving_url(upload.key())
						if request.current.get().isDevServer:
							# NOTE: changed for Ticket ADMIN-37
							servingURL = urlparse(servingURL).path
						elif servingURL.startswith("http://"):
							# Rewrite Serving-URLs to https if we are live
							servingURL = servingURL.replace("http://", "https://")
					except:
						servingURL = ""
				else:
					servingURL = ""
				fileSkel = self.addLeafSkel()
				try:
					# only fetching the file header or all if the file is smaller than 1M
					data = blobstore.fetch_data(upload.key(), 0, min(upload.size, 1000000))
					image = images.Image(image_data=data)
					height = image.height
					width = image.width
				except Exception, err:
					height = width = 0
					logging.error(
						"some error occurred while trying to fetch the image header with dimensions")
					logging.exception(err)

				fileSkel.setValues(
					{
						"name": utils.escapeString(fileName),
						"size": upload.size,
						"mimetype": utils.escapeString(upload.content_type),
						"dlkey": str(upload.key()),
						"servingurl": servingURL,
						"parentdir": parentDir,
						"parentrepo": parentRepo,
						"weak": weak,
						"width": width,
						"height": height
					}
				)
				fileSkel.toDB()
				res.append(fileSkel)
				self.onItemUploaded(fileSkel)
			# Uploads stored successfully, generate response to the client
			for r in res:
				logging.info("Upload successful: %s (%s)" % (r["name"], r["dlkey"]))
			user = utils.getCurrentUser()
			if user:
				logging.info("User: %s (%s)" % (user["name"], user["key"]))
			return( self.render.addItemSuccess( res ) )
		except Exception, err:
			logging.exception(err)
			for upload in self.getUploads():
				upload.delete()
				utils.markFileForDeletion( str(upload.key() ) )
			raise( errors.InternalServerError() )

	@exposed
	def download(self, blobKey, fileName = "", download = "", *args, **kwargs):
		"""
		Download a file.

		:param blobKey: The unique blob key of the file.
		:type blobKey: str

		:param fileName: Optional filename to provide in the header.
		:type fileName: str

		:param download: Set header to attachment retrival, set explictly to "1" if download is wanted.
		:type download: str
		"""
		if download == "1":
			fname = "".join([c for c in fileName if c in string.ascii_lowercase+string.ascii_uppercase + string.digits+".-_"])
			request.current.get().response.headers.add_header("Content-disposition", ("attachment; filename=%s" % (fname)).encode("UTF-8"))
		info = blobstore.get(blobKey)
		if not info:
			raise errors.NotFound()
		request.current.get().response.clear()
		request.current.get().response.headers['Content-Type'] = str(info.content_type)
		if self.blobCacheTime:
			request.current.get().response.headers['Cache-Control'] = "public, max-age=%s" % self.blobCacheTime
		request.current.get().response.headers[blobstore.BLOB_KEY_HEADER] = str(blobKey)
		return ""


	@exposed
	def view( self, *args, **kwargs ):
		"""
			View or download a file.
		"""
		try:
			return super(File, self).view(*args, **kwargs)
		except (errors.NotFound, errors.NotAcceptable, TypeError) as e:
			if len(args) > 0 and blobstore.get(args[0]):
				raise errors.Redirect("%s/download/%s" % (self.modulePath, args[0]))
			elif len(args) > 1 and blobstore.get(args[1]):
				raise errors.Redirect("%s/download/%s" % (self.modulePath, args[1]))
			elif isinstance( e, TypeError ):
				raise errors.NotFound()
			else:
				raise e

	@exposed
	@forceSSL
	@forcePost
	def add(self, skelType, node, *args, **kwargs):
		# We can't add files directly (they need to be uploaded
		if skelType != "node":
			raise errors.NotAcceptable()
		return super(File, self).add(skelType, node, *args, **kwargs)

	def canViewRootNode( self, repo ):
		user = utils.getCurrentUser()
		return self.isOwnUserRootNode(repo) or (user and "root" in user["access"])

	def canMkDir(self, repo, dirname):
		return self.isOwnUserRootNode(str(repo.key()))

	def canRename(self, repo, src, dest):
		return self.isOwnUserRootNode(str(repo.key()))

	def canCopy(self, srcRepo, destRepo, type, deleteold):
		return self.isOwnUserRootNode(str( srcRepo.key()) and self.isOwnUserRootNode(str(destRepo.key())))

	def canDelete(self, skelType, skel):
		user = utils.getCurrentUser()
		if user and "root" in user["access"]:
			return True
		return self.isOwnUserRootNode(str(skel["key"]))


	def canEdit(self, skelType, skel=None):
		user = utils.getCurrentUser()
		return user and "root" in user["access"]

	def onItemUploaded(self, skel):
		pass

File.json = True
File.html = True


@PeriodicTask( 60*4 )
def startCheckForUnreferencedBlobs():
	"""
		Start searching for blob locks that have been recently freed
	"""
	doCheckForUnreferencedBlobs()


@callDeferred
def doCheckForUnreferencedBlobs(cursor = None):
	def getOldBlobKeysTxn(dbKey):
		obj = db.Get(dbKey)
		res = obj["old_blob_references"] or []
		if obj["is_stale"]:
			db.Delete(dbKey)
		else:
			obj["has_old_blob_references"] = False
			obj["old_blob_references"] = []
			db.Put(obj)
		return res
	gotAtLeastOne = False
	query = db.Query("viur-blob-locks").filter("has_old_blob_references", True).cursor(cursor)
	for lockKey in query.run(100, keysOnly=True):
		gotAtLeastOne = True
		oldBlobKeys = db.RunInTransaction( getOldBlobKeysTxn, lockKey )
		for blobKey in oldBlobKeys:
			if db.Query("viur-blob-locks").filter("active_blob_references =", blobKey).get():
				#This blob is referenced elsewhere
				logging.info("Stale blob is still referenced, %s" % blobKey)
				continue
			# Add a marker and schedule it for deletion
			fileObj = db.Query( "viur-deleted-files" ).filter( "dlkey", blobKey ).get()
			if fileObj: #Its already marked
				logging.info("Stale blob already marked for deletion, %s" % blobKey)
				return
			fileObj = db.Entity("viur-deleted-files")
			fileObj["itercount"] = 0
			fileObj["dlkey"] = str(blobKey)
			logging.info("Stale blob marked dirty, %s" % blobKey)
			db.Put(fileObj)
	newCursor = query.getCursor()
	if gotAtLeastOne and newCursor and newCursor.urlsafe() != cursor:
		doCheckForUnreferencedBlobs(newCursor.urlsafe())


@PeriodicTask(0)
def startCleanupDeletedFiles():
	"""
		Increase deletion counter on each blob currently not referenced and delete
		it if that counter reaches maxIterCount
	"""
	doCleanupDeletedFiles()


@callDeferred
def doCleanupDeletedFiles(cursor = None):
	maxIterCount = 2  # How often a file will be checked for deletion
	gotAtLeastOne = False
	query = db.Query("viur-deleted-files").cursor( cursor )
	for file in query.run(100):
		gotAtLeastOne = True
		if not "dlkey" in file:
			db.Delete(file.key())
		elif db.Query("viur-blob-locks").filter("active_blob_references =", file["dlkey"]).get():
			logging.info("is referenced, %s" % file["dlkey"])
			db.Delete(file.key())
		else:
			if file["itercount"] > maxIterCount:
				logging.info("Finally deleting, %s" % file["dlkey"])
				blobstore.delete(file["dlkey"])
				db.Delete(file.key())
				# There should be exactly 1 or 0 of these
				for f in db.Query("file").filter("dlkey =", file["dlkey"]).iter(keysOnly=True):
					db.Delete(f)
			else:
				logging.error("Increasing count, %s" % file["dlkey"])
				file["itercount"] += 1
				db.Put(file)
	newCursor = query.getCursor()
	if gotAtLeastOne and newCursor and newCursor.urlsafe() != cursor:
		doCleanupDeletedFiles(newCursor.urlsafe())


@PeriodicTask(60*4)
def startDeleteWeakReferences():
	"""
		Delete all weak file references older than a day.
		If that file isn't referenced elsewhere, it's deleted, too.
	"""
	doDeleteWeakReferences((datetime.now() - timedelta(days = 1)).strftime("%d.%m.%Y %H:%M:%S"), None)


@callDeferred
def doDeleteWeakReferences(timeStamp, cursor):
	skelCls = skeletonByKind("file")
	gotAtLeastOne = False
	query = skelCls().all().filter("weak =", True).filter("creationdate <", datetime.strptime(timeStamp,"%d.%m.%Y %H:%M:%S")).cursor(cursor)
	for skel in query.fetch(99):
		# FIXME: Is that still needed? See hotfix/weakfile
		anyRel = any(db.Query("viur-relations").filter("dest.key =", skel["key"]).run(1, keysOnly=True))
		if anyRel:
			logging.debug("doDeleteWeakReferences: found relations with that file - don't delete!")
			continue
		gotAtLeastOne = True
		skel.delete()
	newCursor = query.getCursor()
	if gotAtLeastOne and newCursor and newCursor.urlsafe() != cursor:
		doDeleteWeakReferences(timeStamp, newCursor.urlsafe())
