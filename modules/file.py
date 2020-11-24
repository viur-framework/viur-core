# -*- coding: utf-8 -*-

import base64
import email.header
import json
import logging
from base64 import urlsafe_b64decode
from datetime import datetime, timedelta
from io import BytesIO
from quopri import decodestring
from typing import Dict, Tuple, Union

import google.auth
from PIL import Image
from google.auth import compute_engine
from google.auth.transport import requests
from google.cloud import storage
from google.cloud._helpers import _NOW, _datetime_to_rfc3339
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

from viur.core import db, errors, exposed, forcePost, forceSSL, internalExposed, securitykey, utils
from viur.core.bones import *
from viur.core.prototypes.tree import Tree, TreeSkel, TreeType
from viur.core.skeleton import skeletonByKind
from viur.core.tasks import PeriodicTask, callDeferred
from viur.core.utils import projectID

credentials, project = google.auth.default()
client = storage.Client(project, credentials)
bucket = client.lookup_bucket("%s.appspot.com" % projectID)


class injectStoreURLBone(baseBone):
	def unserialize(self, skel, name):
		if "dlkey" in skel.dbEntity and "name" in skel.dbEntity:
			skel.accessedValues[name] = utils.downloadUrlFor(skel["dlkey"], skel["name"], derived=False)
			return True
		return False


def thumbnailer(fileSkel, targetName, params):
	blob = bucket.get_blob("%s/source/%s" % (fileSkel["dlkey"], fileSkel["name"]))
	fileData = BytesIO()
	outData = BytesIO()
	blob.download_to_file(fileData)
	fileData.seek(0)
	img = Image.open(fileData)
	if "size" in params:
		img.thumbnail(params["size"])
	elif "width" in params:
		img = img.resize((params["width"], int((float(img.size[1]) * float(params["width"] / float(img.size[0]))))),
						 Image.ANTIALIAS)
	img.save(outData, "JPEG")
	outSize = outData.tell()
	outData.seek(0)
	targetBlob = bucket.blob("%s/derived/%s" % (fileSkel["dlkey"], targetName))
	targetBlob.upload_from_file(outData, content_type="image/jpeg")
	return targetName, outSize, "image/jpeg"


class fileBaseSkel(TreeSkel):
	"""
		Default file leaf skeleton.
	"""
	kindName = "file"

	size = stringBone(descr="Size", readOnly=True, indexed=True, searchable=True)
	dlkey = stringBone(descr="Download-Key", readOnly=True, indexed=True)
	name = stringBone(descr="Filename", caseSensitive=False, indexed=True, searchable=True)
	mimetype = stringBone(descr="Mime-Info", readOnly=True, indexed=True)
	weak = booleanBone(descr="Weak reference", indexed=True, readOnly=True, visible=False)
	pending = booleanBone(descr="Pending upload", readOnly=True, visible=False, defaultValue=False)
	width = numericBone(descr="Width", indexed=True, readOnly=True, searchable=True)
	height = numericBone(descr="Height", indexed=True, readOnly=True, searchable=True)
	downloadUrl = injectStoreURLBone(descr="Download-URL", readOnly=True, visible=False)
	derived = baseBone(descr=u"Derived Files", readOnly=True, visible=False)
	pendingparententry = keyBone(descr=u"Pending key Reference", readOnly=True, visible=False)

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
		if not self["weak"] and self["dlkey"]:
			locks.add(self["dlkey"])
		return locks


class fileNodeSkel(TreeSkel):
	"""
		Default file node skeleton.
	"""
	kindName = "file_rootNode"
	name = stringBone(descr="Name", required=True, indexed=True, searchable=True)
	rootNode = booleanBone(descr=u"Is RootNode", indexed=True)


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
	leafSkelCls = fileBaseSkel
	nodeSkelCls = fileNodeSkel

	maxuploadsize = None
	uploadHandler = []

	adminInfo = {
		"name": "File",
		"handler": "tree.simple.file",
		"icon": "icons/modules/my_files.svg"
	}

	blobCacheTime = 60 * 60 * 24  # Requests to file/download will be served with cache-control: public, max-age=blobCacheTime if set

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

	def generateUploadPolicy(self, conditions):
		"""
		Our implementation of bucket.generate_upload_policy - which works with default token credentials
		Create a signed upload policy for uploading objects.

		This method generates and signs a policy document. You can use
		`policy documents`_ to allow visitors to a website to upload files to
		Google Cloud Storage without giving them direct write access.

		For example:

		.. literalinclude:: snippets.py
			:start-after: [START policy_document]
			:end-before: [END policy_document]

		.. _policy documents:
			https://cloud.google.com/storage/docs/xml-api\
			/post-object#policydocument

		:type expiration: datetime
		:param expiration: Optional expiration in UTC. If not specified, the
						   policy will expire in 1 hour.

		:type conditions: list
		:param conditions: A list of conditions as described in the
						  `policy documents`_ documentation.

		:type client: :class:`~google.cloud.storage.client.Client`
		:param client: Optional. The client to use.  If not passed, falls back
					   to the ``client`` stored on the current bucket.

		:rtype: dict
		:returns: A dictionary of (form field name, form field value) of form
				  fields that should be added to your HTML upload form in order
				  to attach the signature.
		"""
		global credentials, bucket
		auth_request = requests.Request()
		sign_cred = compute_engine.IDTokenCredentials(auth_request, "",
													  service_account_email=credentials.service_account_email)
		expiration = _NOW() + timedelta(hours=1)
		conditions = conditions + [{"bucket": bucket.name}]
		policy_document = {
			"expiration": _datetime_to_rfc3339(expiration),
			"conditions": conditions,
		}
		encoded_policy_document = base64.b64encode(
			json.dumps(policy_document).encode("utf-8")
		)
		signature = base64.b64encode(sign_cred.sign_bytes(encoded_policy_document))
		fields = {
			"bucket": bucket.name,
			"GoogleAccessId": sign_cred.signer_email,
			"policy": encoded_policy_document.decode("utf-8"),
			"signature": signature.decode("utf-8"),
		}
		return fields

	def createUploadURL(self, node: Union[str, None]) -> Tuple[str, str, Dict[str, str]]:
		global bucket
		targetKey = utils.generateRandomString()
		conditions = [["starts-with", "$key", "%s/source/" % targetKey]]
		if isinstance(credentials, ServiceAccountCredentials):  # We run locally with an service-account.json
			policy = bucket.generate_upload_policy(conditions)
		else:  # Use our fixed PolicyGenerator - Google is currently unable to create one itself on its GCE
			policy = self.generateUploadPolicy(conditions)
		uploadUrl = "https://%s.storage.googleapis.com" % bucket.name
		# Create a correspondingfile-lock object early, otherwise we would have to ensure that the file-lock object
		# the user creates matches the file he had uploaded
		fileSkel = self.addSkel(TreeType.Leaf)
		fileSkel["key"] = targetKey
		fileSkel["name"] = "pending"
		fileSkel["size"] = 0
		fileSkel["mimetype"] = "application/octetstream"
		fileSkel["dlkey"] = targetKey
		fileSkel["parentdir"] = None
		fileSkel["pendingparententry"] = db.keyHelper(node, self.addSkel(TreeType.Node).kindName) if node else None
		fileSkel["pending"] = True
		fileSkel["weak"] = True
		fileSkel["width"] = 0
		fileSkel["height"] = 0
		fileSkel.toDB()
		# Mark that entry dirty as we might never receive an add
		utils.markFileForDeletion(targetKey)
		return targetKey, uploadUrl, policy

	@exposed
	def getUploadURL(self, *args, **kwargs):
		skey = kwargs.get("skey", "")
		node = kwargs.get("node")
		if node:
			rootNode = self.getRootNode(node)
			if not self.canAdd(TreeType.Leaf, rootNode):
				raise errors.Forbidden()
		else:
			if not self.canAdd(TreeType.Leaf, None):
				raise errors.Forbidden()
		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()
		targetKey, uploadUrl, policy = self.createUploadURL(node)
		resDict = {
			"url": uploadUrl,
			"params": {
				"key": "%s/source/file.dat" % targetKey,
			}
		}
		for key, value in policy.items():
			resDict["params"][key] = value
		return self.render.view(resDict)

	@internalExposed
	def getAvailableRootNodes__(self, name, *args, **kwargs):
		thisuser = utils.getCurrentUser()
		if not thisuser:
			return []
		repo = self.ensureOwnUserRootNode()
		res = [{
			"name": str("My Files"),
			"key": str(repo.key.id_or_name)
		}]
		if 0 and "root" in thisuser["access"]:  # FIXME!
			# Add at least some repos from other users
			repos = db.Query(self.viewNodeSkel.kindName + "_rootNode").filter("type =", "user").run(100)
			for repo in repos:
				if not "user" in repo:
					continue
				user = db.Query("user").filter("uid =", repo.user).getEntry()
				if not user or not "name" in user:
					continue
				res.append({
					"name": user["name"],
					"key": str(repo.key())
				})
		return res

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
		global credentials, bucket
		if not sig:
			raise errors.PreconditionFailed()
		# First, validate the signature, otherwise we don't need to proceed any further
		if not utils.hmacVerify(blobKey.encode("ASCII"), sig):
			raise errors.Forbidden()
		# Split the blobKey into the individual fields it should contain
		dlPath, validUntil = urlsafe_b64decode(blobKey).decode("UTF-8").split("\0")
		if validUntil != "0" and datetime.strptime(validUntil, "%Y%m%d%H%M") < datetime.now():
			raise errors.Gone()
		# Create a signed url and redirect the user
		if isinstance(credentials, ServiceAccountCredentials):  # We run locally with an service-account.json
			blob = bucket.get_blob(dlPath)
			if not blob:
				raise errors.NotFound()
			signed_url = blob.generate_signed_url(datetime.now() + timedelta(seconds=60))
		else:  # We are inside the appengine
			if validUntil == "0":  # Its an indefinitely valid URL
				blob = bucket.get_blob(dlPath)
				if blob.size < 5 * 1024 * 1024:  # Less than 5 MB - Serve directly and push it into the ede caches
					response = utils.currentRequest.get().response
					response.headers["Content-Type"] = blob.content_type
					response.headers["Cache-Control"] = "public, max-age=604800"  # 7 Days
					return blob.download_as_bytes()
			auth_request = requests.Request()
			signed_blob_path = bucket.blob(dlPath)
			expires_at_ms = datetime.now() + timedelta(seconds=60)
			signing_credentials = compute_engine.IDTokenCredentials(auth_request, "",
																	service_account_email=credentials.service_account_email)
			signed_url = signed_blob_path.generate_signed_url(expires_at_ms, credentials=signing_credentials,
															  version="v4")
		raise errors.Redirect(signed_url)

	@exposed
	@forceSSL
	@forcePost
	def add(self, skelType, node=None, *args, **kwargs):
		## We can't add files directly (they need to be uploaded
		# if skelType != "node":
		#	raise errors.NotAcceptable()
		if skelType == "leaf":  # We need to handle leafs separately here
			skey = kwargs.get("skey")
			targetKey = kwargs.get("key")
			if not skey or not securitykey.validate(skey, useSessionKey=True) or not targetKey:
				raise errors.PreconditionFailed()
			skel = self.addSkel(TreeType.Leaf)
			if not skel.fromDB(targetKey):
				raise errors.NotFound()
			if not skel["pending"]:
				raise errors.PreconditionFailed()
			skel["pending"] = False
			skel["parententry"] = skel["pendingparententry"]
			if skel["parententry"]:
				rootNode = self.getRootNode(skel["parententry"])
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
			skel["rootnode"] = rootNode["key"] if rootNode else None
			skel["weak"] = rootNode is None
			skel.toDB()
			# Add updated download-URL as the auto-generated isn't valid yet
			skel["downloadUrl"] = utils.downloadUrlFor(skel["dlkey"], skel["name"], derived=False)
			return self.render.addSuccess(skel)
		return super(File, self).add(skelType, node, *args, **kwargs)

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

	query = db.Query("viur-blob-locks").filter("has_old_blob_references", True).setCursor(cursor)
	for lockObj in query.run(100):
		oldBlobKeys = db.RunInTransaction(getOldBlobKeysTxn, lockObj.key)
		for blobKey in oldBlobKeys:
			if db.Query("viur-blob-locks").filter("active_blob_references =", blobKey).getEntry():
				# This blob is referenced elsewhere
				logging.info("Stale blob is still referenced, %s" % blobKey)
				continue
			# Add a marker and schedule it for deletion
			fileObj = db.Query("viur-deleted-files").filter("dlkey", blobKey).getEntry()
			if fileObj:  # Its already marked
				logging.info("Stale blob already marked for deletion, %s" % blobKey)
				return
			fileObj = db.Entity(db.Key("viur-deleted-files"))
			fileObj["itercount"] = 0
			fileObj["dlkey"] = str(blobKey)
			logging.info("Stale blob marked dirty, %s" % blobKey)
			db.Put(fileObj)
	newCursor = query.getCursor()
	if newCursor:
		doCheckForUnreferencedBlobs(newCursor)


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
	query = db.Query("viur-deleted-files")
	if cursor:
		query.setCursor(cursor)
	for file in query.run(100):
		if not "dlkey" in file:
			db.Delete(file.key)
		elif db.Query("viur-blob-locks").filter("active_blob_references =", file["dlkey"]).getEntry():
			logging.info("is referenced, %s" % file["dlkey"])
			db.Delete(file.key)
		else:
			if file["itercount"] > maxIterCount:
				logging.info("Finally deleting, %s" % file["dlkey"])
				blobs = bucket.list_blobs(prefix="%s/" % file["dlkey"])
				for blob in blobs:
					blob.delete()
				db.Delete(file.key)
				# There should be exactly 1 or 0 of these
				for f in skeletonByKind("file")().all().filter("dlkey =", file["dlkey"]).fetch(99):
					f.delete()
			else:
				logging.debug("Increasing count, %s" % file["dlkey"])
				file["itercount"] += 1
				db.Put(file)
	newCursor = query.getCursor()
	if newCursor:
		doCleanupDeletedFiles(newCursor)
