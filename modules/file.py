# -*- coding: utf-8 -*-

from viur.server import utils, db, securitykey, session, errors, conf, request, forcePost, forceSSL, exposed, internalExposed
from viur.server.skeleton import Skeleton, skeletonByKind
from viur.server.bones import *
from viur.server.prototypes.tree import Tree, TreeNodeSkel, TreeLeafSkel
from viur.server.tasks import callDeferred, PeriodicTask
from quopri import decodestring
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
import email.header
import collections, logging, cgi, string
from google.auth import compute_engine
from datetime import datetime, timedelta
from google.cloud import storage
from viur.server.utils import projectID
import hashlib
import hmac
from io import BytesIO
from PIL import Image

client = storage.Client.from_service_account_json("store_credentials.json")
bucket = client.lookup_bucket("%s.appspot.com" % projectID)
conf["viur.file.hmacKey"] = hashlib.sha3_384(
	open("store_credentials.json", "rb").read()).digest()  # FIXME: Persistent key from db?



class injectStoreURLBone(baseBone):
	def unserialize(self, valuesCache, name, expando):
		if "dlkey" in expando and "name" in expando:
			valuesCache[name] = utils.downloadUrlFor(expando["dlkey"], expando["name"], derived=False)


def thumbnailer(dlKey, origName, targetName, params, size):
	blob = bucket.get_blob("%s/source/%s" % (dlKey, origName))
	fileData = BytesIO()
	outData = BytesIO()
	blob.download_to_file(fileData)
	fileData.seek(0)
	img = Image.open(fileData)
	img.thumbnail(size)
	img.save(outData, "JPEG")
	outData.seek(0)
	targetBlob = bucket.blob("%s/derived/%s" % (dlKey, targetName))
	targetBlob.upload_from_file(outData, content_type="image/jpeg")
	return targetName

class fileBaseSkel(TreeLeafSkel):
	"""
		Default file leaf skeleton.
	"""
	kindName = "file"

	size = stringBone(descr="Size", readOnly=True, indexed=True, searchable=True)
	dlkey = stringBone(descr="Download-Key", readOnly=True, indexed=True)
	name = stringBone(descr="Filename", caseSensitive=False, indexed=True, searchable=True)
	mimetype = stringBone(descr="Mime-Info", readOnly=True, indexed=True)
	weak = booleanBone(descr="Weak reference", indexed=True, readOnly=True, visible=False)
	pending = booleanBone(descr="Pending upload", readOnly=True, visible=False)
	servingurl = stringBone(descr="Serving URL", readOnly=True)
	width = numericBone(descr="Width", indexed=True, readOnly=True, searchable=True)
	height = numericBone(descr="Height", indexed=True, readOnly=True, searchable=True)
	downloadUrl = injectStoreURLBone(descr="Download-URL", readOnly=True, visible=False)
	derived = baseBone(descr=u"Derived Files", readOnly=True, visible=False)

	"""
	def refresh(self):
		# Update from blobimportmap
		try:
			oldKeyHash = sha256(self["dlkey"]).hexdigest().encode("hex")
			res = db.Get(db.Key.from_path("viur-blobimportmap", oldKeyHash))
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
	"""

	def preProcessBlobLocks(self, locks):
		"""
			Ensure that our dlkey is locked even if we don't have a filebone here
		"""
		if not self["weak"]:
			locks.add(self["dlkey"])
		return locks


class fileNodeSkel(TreeNodeSkel):
	"""
		Default file node skeleton.
	"""
	kindName = "file_rootNode"
	name = stringBone(descr="Name", required=True, indexed=True, searchable=True)


def decodeFileName(name):
	# http://code.google.com/p/googleappengine/issues/detail?id=2749
	# Open since Sept. 2010, claimed to be fixed in Version 1.7.2 (September 18, 2012)
	# and still totally broken
	try:
		if name.startswith("=?"):  # RFC 2047
			return str(email.Header.make_header(email.Header.decode_header(name + "\n")))
		elif "=" in name and not name.endswith("="):  # Quoted Printable
			return decodestring(name.encode("ascii")).decode("UTF-8")
		else:  # Maybe base64 encoded
			return urlsafe_b64decode(name.encode("ascii")).decode("UTF-8")
	except:  # Sorry - I cant guess whats happend here
		if isinstance(name, str) and not isinstance(name, str):
			try:
				return name.decode("UTF-8", "ignore")
			except:
				pass

		return name


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

	blobCacheTime = 60 * 60 * 24  # Requests to file/download will be served with cache-control: public, max-age=blobCacheTime if set

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
		files = db.Query(self.editLeafSkel().kindName).filter("parentdir =", parentKey).iter()
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
	def getUploadURL(self, *args, **kwargs):
		skey = kwargs.get("skey", "")
		node = kwargs.get("node")
		if node:
			rootNode = self.getRootNode(node)
			if not self.canAdd("leaf", rootNode):
				raise errors.Forbidden()
		else:
			if not self.canAdd("leaf", None):
				raise errors.Forbidden()
		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()

		targetKey = utils.generateRandomString()
		conditions = [["starts-with", "$key", "%s/source/" % targetKey]]

		policy = bucket.generate_upload_policy(conditions)
		uploadUrl = "https://%s.storage.googleapis.com" % bucket.name
		resDict = {
			"url": uploadUrl,
			"params": {
				"key": "%s/source/file.dat" % targetKey,
			}
		}
		for key, value in policy.items():
			resDict["params"][key] = value

		# Create a correspondingfile-lock object early, otherwise we would have to ensure that the file-lock object
		# the user creates matches the file he had uploaded

		fileSkel = self.addLeafSkel()
		fileSkel["key"] = targetKey

		fileSkel.setValues(
			{
				"name": "pending",
				"size": 0,
				"mimetype": "application/octetstream",
				"dlkey": targetKey,
				"servingurl": "",
				"parentdir": "pending-%s" % utils.escapeString(node) if node else "",
				"parentrepo": "",
				"weak": True,
				"width": 0,
				"height": 0
			}
		)
		fileSkel.toDB()
		# Mark that entry dirty as we might never receive an add
		utils.markFileForDeletion(targetKey)

		return self.render.view(resDict)

	@internalExposed
	def getAvailableRootNodes(self, name, *args, **kwargs):
		thisuser = utils.getCurrentUser()
		if not thisuser:
			return []
		repo = self.ensureOwnUserRootNode()
		res = [{
			"name": str("My Files"),
			"key": str(repo.name)
		}]
		if 0 and "root" in thisuser["access"]:  # FIXME!
			# Add at least some repos from other users
			repos = db.Query(self.viewNodeSkel.kindName + "_rootNode").filter("type =", "user").run(100)
			for repo in repos:
				if not "user" in repo:
					continue
				user = db.Query("user").filter("uid =", repo.user).get()
				if not user or not "name" in user:
					continue
				res.append({
					"name": user["name"],
					"key": str(repo.key())
				})
		return res

	@exposed
	def upload(self, node=None, *args, **kwargs):
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
					parentRepo = nodeSkel["parentrepo"]
			else:
				weak = True
				parentDir = None
				parentRepo = None

			# Handle the actual uploads
			for upload in self.getUploads():
				fileName = decodeFileName(upload.filename)
				height = width = 0

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

					try:
						# only fetching the file header or all if the file is smaller than 1M
						data = blobstore.fetch_data(upload.key(), 0, min(upload.size, 1000000))
						image = images.Image(image_data=data)
						height = image.height
						width = image.width
					except Exception as err:
						logging.error("some error occurred while trying to fetch the image header with dimensions")
						logging.exception(err)

				else:
					servingURL = ""

				fileSkel = self.addLeafSkel()

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

			return self.render.addItemSuccess(res)

		except Exception as err:
			logging.exception(err)

			for upload in self.getUploads():
				upload.delete()
				utils.markFileForDeletion(str(upload.key()))

			raise errors.InternalServerError()

	@exposed
	def download(self, blobKey, fileName="", download="", sig="", *args, **kwargs):
		"""
		Download a file.

		:param blobKey: The unique blob key of the file.
		:type blobKey: str

		:param fileName: Optional filename to provide in the header.
		:type fileName: str

		:param download: Set header to attachment retrival, set explictly to "1" if download is wanted.
		:type download: str
		"""
		if not sig:
			raise errors.PreconditionFailed()
		# if download == "1":
		#	fname = "".join(
		#		[c for c in fileName if c in string.ascii_lowercase + string.ascii_uppercase + string.digits + ".-_"])
		#	request.current.get().response.headers.add_header("Content-disposition",
		#													  ("attachment; filename=%s" % (fname)).encode("UTF-8"))
		# First, validate the signature, otherwise we don't need to proceed any further
		if not utils.hmacVerify(blobKey.encode("ASCII"), sig):
			raise errors.Forbidden()
		# Split the blobKey into the individual fields it should contain
		dlPath, validUntil = urlsafe_b64decode(blobKey).decode("UTF-8").split("\0")
		if validUntil != "0" and datetime.strptime(validUntil, "%Y%m%d%H%M") < datetime.now():
			raise errors.Gone()
		# Create a signed url and redirect the user
		blob = bucket.get_blob(dlPath)
		if not blob:
			raise errors.NotFound()
		signed_url = blob.generate_signed_url(datetime.now() + timedelta(seconds=60))
		raise errors.Redirect(signed_url)


	@exposed
	@forceSSL
	@forcePost
	def add(self, skelType, node, *args, **kwargs):
		## We can't add files directly (they need to be uploaded
		# if skelType != "node":
		#	raise errors.NotAcceptable()
		if skelType == "leaf":  # We need to handle leafs separately here
			skey = kwargs.get("skey")
			targetKey = kwargs.get("key")
			if not skey or not securitykey.validate(skey, useSessionKey=True) or not targetKey:
				raise errors.PreconditionFailed()

			skel = self.addLeafSkel()
			if not skel.fromDB(targetKey):
				raise errors.NotFound()
			if not skel["parentdir"].startswith("pending-"):
				raise errors.PreconditionFailed()
			skel["parentdir"] = skel["parentdir"][8:]
			if skel["parentdir"]:
				rootNode = self.getRootNode(skel["parentdir"])
			else:
				rootNode = None
			if not self.canAdd("leaf", rootNode):
				raise errors.Forbidden()
			blobs = list(bucket.list_blobs(prefix="%s/" % targetKey))
			if len(blobs) != 1:
				logging.error("Invalid number of blobs in folder")
				logging.error(targetKey)
				raise errors.PreconditionFailed()
			blob = blobs[0]
			skel["mimetype"] = utils.escapeString(blob.content_type)
			skel["name"] = utils.escapeString(blob.name.replace("%s/source/" % targetKey, ""))
			skel["size"] = blob.size
			skel["rootnode"] = rootNode
			skel["weak"] = rootNode is None
			skel.toDB()
			# Add updated download-URL as the auto-generated isn't valid yet
			skel["downloadUrl"] = utils.downloadUrlFor(skel["dlkey"], skel["name"], derived=False)
			return self.render.addItemSuccess(skel)

		return super(File, self).add(skelType, node, *args, **kwargs)

	def canViewRootNode(self, repo):
		user = utils.getCurrentUser()
		return self.isOwnUserRootNode(repo) or (user and "root" in user["access"])

	def canMkDir(self, repo, dirname):
		return self.isOwnUserRootNode(str(repo.key()))

	def canRename(self, repo, src, dest):
		return self.isOwnUserRootNode(str(repo.key()))

	def canCopy(self, srcRepo, destRepo, type, deleteold):
		return self.isOwnUserRootNode(str(srcRepo.key()) and self.isOwnUserRootNode(str(destRepo.key())))

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


@PeriodicTask(60 * 4)
def startCheckForUnreferencedBlobs():
	"""
		Start searching for blob locks that have been recently freed
	"""
	doCheckForUnreferencedBlobs()


@callDeferred
def doCheckForUnreferencedBlobs(cursor=None):
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
		oldBlobKeys = db.RunInTransaction(getOldBlobKeysTxn, lockKey)
		for blobKey in oldBlobKeys:
			if db.Query("viur-blob-locks").filter("active_blob_references =", blobKey).get():
				# This blob is referenced elsewhere
				logging.info("Stale blob is still referenced, %s" % blobKey)
				continue
			# Add a marker and schedule it for deletion
			fileObj = db.Query("viur-deleted-files").filter("dlkey", blobKey).get()
			if fileObj:  # Its already marked
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
def doCleanupDeletedFiles(cursor=None):
	maxIterCount = 2  # How often a file will be checked for deletion
	gotAtLeastOne = False
	query = db.Query("viur-deleted-files")
	if cursor:
		query.cursor(cursor)
	for file in query.run(100):
		gotAtLeastOne = True
		if not "dlkey" in file:
			db.Delete((file.collection, file.name))
		elif db.Query("viur-blob-locks").filter("active_blob_references AC", file["dlkey"]).get():
			logging.info("is referenced, %s" % file["dlkey"])
			db.Delete((file.collection, file.name))
		else:
			if file["itercount"] > maxIterCount:
				logging.info("Finally deleting, %s" % file["dlkey"])
				blobs = bucket.list_blobs(prefix="%s/" % file["dlkey"])
				for blob in blobs:
					blob.delete()
				db.Delete((file.collection, file.name))
				# There should be exactly 1 or 0 of these
				for f in skeletonByKind("file")().all().filter("dlkey =", file["dlkey"]).fetch(99):
					f.delete()
			else:
				logging.debug("Increasing count, %s" % file["dlkey"])
				file["itercount"] += 1
				db.Put(file)
	#newCursor = query.getCursor()
	#if gotAtLeastOne and newCursor and newCursor.urlsafe() != cursor:
	#	doCleanupDeletedFiles(newCursor.urlsafe())

