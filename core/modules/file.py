import base64
import email.header
import google.auth
import json
import logging
import string
import html
from PIL import Image, ImageCms
from base64 import urlsafe_b64decode
from datetime import datetime, timedelta
from google.auth import compute_engine
from google.auth.transport import requests
from google.cloud import iam_credentials_v1, storage
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from io import BytesIO
from quopri import decodestring
from typing import Any, List, Tuple, Union
from urllib.request import urlopen
from viur.core import db, conf, errors, exposed, forcePost, forceSSL, securitykey, utils
from viur.core.bones import BaseBone, BooleanBone, KeyBone, NumericBone, StringBone
from viur.core.prototypes.tree import SkelType, Tree, TreeSkel
from viur.core.skeleton import skeletonByKind
from viur.core.tasks import PeriodicTask, CallDeferred
from viur.core.utils import sanitizeFileName

credentials, project = google.auth.default()
client = storage.Client(project, credentials)
bucket = client.lookup_bucket(f"""{conf["viur.instance.project_id"]}.appspot.com""")
iamClient = iam_credentials_v1.IAMCredentialsClient()


def importBlobFromViur2(dlKey, fileName):
    if not conf.get("viur.viur2import.blobsource"):
        return False
    existingImport = db.Get(db.Key("viur-viur2-blobimport", dlKey))
    if existingImport:
        if existingImport["success"]:
            return existingImport["dlurl"]
        return False
    if conf["viur.viur2import.blobsource"]["infoURL"]:
        try:
            importDataReq = urlopen(conf["viur.viur2import.blobsource"]["infoURL"] + dlKey)
        except:
            marker = db.Entity(db.Key("viur-viur2-blobimport", dlKey))
            marker["success"] = False
            marker["error"] = "Failed URL-FETCH 1"
            db.Put(marker)
            return False
        if importDataReq.status != 200:
            marker = db.Entity(db.Key("viur-viur2-blobimport", dlKey))
            marker["success"] = False
            marker["error"] = "Failed URL-FETCH 2"
            db.Put(marker)
            return False
        importData = json.loads(importDataReq.read())
        oldBlobName = conf["viur.viur2import.blobsource"]["gsdir"] + "/" + importData["key"]
        srcBlob = storage.Blob(bucket=bucket,
                               name=conf["viur.viur2import.blobsource"]["gsdir"] + "/" + importData["key"])
    else:
        oldBlobName = conf["viur.viur2import.blobsource"]["gsdir"] + "/" + dlKey
        srcBlob = storage.Blob(bucket=bucket, name=conf["viur.viur2import.blobsource"]["gsdir"] + "/" + dlKey)
    if not srcBlob.exists():
        marker = db.Entity(db.Key("viur-viur2-blobimport", dlKey))
        marker["success"] = False
        marker["error"] = "Local SRC-Blob missing"
        marker["oldBlobName"] = oldBlobName
        db.Put(marker)
        return False
    bucket.rename_blob(srcBlob, "%s/source/%s" % (dlKey, fileName))
    marker = db.Entity(db.Key("viur-viur2-blobimport", dlKey))
    marker["success"] = True
    marker["old_src_key"] = dlKey
    marker["old_src_name"] = fileName
    marker["dlurl"] = utils.downloadUrlFor(dlKey, fileName, False, None)
    db.Put(marker)
    return marker["dlurl"]


class InjectStoreURLBone(BaseBone):

    def unserialize(self, skel, name):
        if "dlkey" in skel.dbEntity and "name" in skel.dbEntity:
            skel.accessedValues[name] = utils.downloadUrlFor(
                skel["dlkey"], skel["name"], derived=False, expires=conf["viur.render.json.downloadUrlExpiration"]
            )
            return True
        return False


def thumbnailer(fileSkel, existingFiles, params):
    file_name = html.unescape(fileSkel["name"])
    blob = bucket.get_blob("%s/source/%s" % (fileSkel["dlkey"], file_name))
    if not blob:
        logging.warning("Blob %s/source/%s is missing from cloud storage!" % (fileSkel["dlkey"], file_name))
        return
    fileData = BytesIO()
    blob.download_to_file(fileData)
    resList = []
    for sizeDict in params:
        fileData.seek(0)
        outData = BytesIO()
        try:
            img = Image.open(fileData)
        except Image.UnidentifiedImageError:  # We can't load this image; so there's no need to try other resolutions
            return []
        iccProfile = img.info.get('icc_profile')
        if iccProfile:
            # JPEGs might be encoded with a non-standard color-profile; we need to compensate for this if we convert
            # to WEBp as we'll loose this color-profile information
            f = BytesIO(iccProfile)
            src_profile = ImageCms.ImageCmsProfile(f)
            dst_profile = ImageCms.createProfile('sRGB')
            img = ImageCms.profileToProfile(img, inputProfile=src_profile, outputProfile=dst_profile, outputMode="RGB")
        fileExtension = sizeDict.get("fileExtension", "webp")
        if "width" in sizeDict and "height" in sizeDict:
            width = sizeDict["width"]
            height = sizeDict["height"]
            targetName = "thumbnail-%s-%s.%s" % (width, height, fileExtension)
        elif "width" in sizeDict:
            width = sizeDict["width"]
            height = int((float(img.size[1]) * float(width / float(img.size[0]))))
            targetName = "thumbnail-w%s.%s" % (width, fileExtension)
        else:  # No default fallback - ignore
            continue
        mimeType = sizeDict.get("mimeType", "image/webp")
        img = img.resize((width, height), Image.ANTIALIAS)
        img.save(outData, fileExtension)
        outSize = outData.tell()
        outData.seek(0)
        targetBlob = bucket.blob("%s/derived/%s" % (fileSkel["dlkey"], targetName))
        targetBlob.upload_from_file(outData, content_type=mimeType)
        resList.append((targetName, outSize, mimeType, {"mimetype": mimeType, "width": width, "height": height}))
    return resList


def cloudfunction_thumbnailer(fileSkel, existingFiles, params):
    """External Thumbnailer for images.

       The corresponding cloudfunction can be found here .
       https://github.com/viur-framework/viur-cloudfunctions/tree/main/thumbnailer

       You can use it like so:
       main.py:

       from viur.core.modules.file import cloudfunction_thumbnailer

       conf["viur.file.thumbnailerURL"]="https://xxxxx.cloudfunctions.net/imagerenderer"
       conf["viur.file.derivers"] = {"thumbnail": cloudfunction_thumbnailer}

       conf["derives_pdf"] = {
       "thumbnail": [{"width": 1920,"sites":"1,2"}]
       }
       skeletons/xxx.py:

       test = FileBone(derive=conf["derives_pdf"])
       """

    if not conf.get("viur.file.thumbnailerURL", False):
        raise ValueError("viur.file.thumbnailerURL is not set")

    def getsignedurl():
        if conf["viur.instance.is_dev_server"]:
            signedUrl = utils.downloadUrlFor(fileSkel["dlkey"], fileSkel["name"])
        else:
            path = f"""{fileSkel["dlkey"]}/source/{file_name}"""
            if not (blob := bucket.get_blob(path)):
                logging.warning(f"Blob {path} is missing from cloud storage!")
                return None
            authRequest = requests.Request()
            expiresAt = datetime.now() + timedelta(seconds=60)
            signing_credentials = compute_engine.IDTokenCredentials(authRequest, "")
            contentDisposition = "filename=%s" % fileSkel["name"]
            signedUrl = blob.generate_signed_url(
                expiresAt,
                credentials=signing_credentials,
                response_disposition=contentDisposition,
                version="v4")
        return signedUrl

    def make_request():
        import requests as _requests
        headers = {"Content-Type": "application/json"}
        data_str = base64.b64encode(json.dumps(dataDict).encode("UTF-8"))
        sig = utils.hmacSign(data_str)
        datadump = json.dumps({"dataStr": data_str.decode('ASCII'), "sign": sig})
        resp = _requests.post(conf["viur.file.thumbnailerURL"], data=datadump, headers=headers, allow_redirects=False)
        if resp.status_code != 200:  # Error Handling
            match resp.status_code:
                case 302:
                    # The problem is Google resposen 302 to an auth Site when the cloudfunction was not found
                    # https://cloud.google.com/functions/docs/troubleshooting#login
                    logging.error("Cloudfunction not found")
                case 404:
                    logging.error("Cloudfunction not found")
                case 403:
                    logging.error("No permission for the Cloudfunction")
                case _:
                    logging.error(
                        f"cloudfunction_thumbnailer failed with code: {resp.status_code} and data: {resp.content}")
            return

        try:
            response_data = resp.json()
        except Exception as e:
            logging.error(f"response could not be converted in json failed with: {e=}")
            return
        if "error" in response_data:
            logging.error(f"cloudfunction_thumbnailer failed with: {response_data.get('error')}")
            return

        return response_data

    file_name = html.unescape(fileSkel["name"])

    if not (url := getsignedurl()):
        return
    dataDict = {
        "url": url,
        "name": fileSkel["name"],
        "params": params,
        "minetype": fileSkel["mimetype"],
        "baseUrl": utils.currentRequest.get().request.host_url.lower(),
        "targetKey": fileSkel["dlkey"],
        "nameOnly": True
    }
    if not (derivedData := make_request()):
        return

    uploadUrls = {}
    for data in derivedData["values"]:
        fileName = sanitizeFileName(data["name"])
        blob = bucket.blob("%s/derived/%s" % (fileSkel["dlkey"], fileName))
        uploadUrls[fileSkel["dlkey"] + fileName] = blob.create_resumable_upload_session(timeout=60,
                                                                                        content_type=data["mimeType"])

    if not (url := getsignedurl()):
        return

    dataDict["url"] = url
    dataDict["nameOnly"] = False
    dataDict["uploadUrls"] = uploadUrls

    if not (derivedData := make_request()):
        return
    reslist = []
    try:
        for derived in derivedData["values"]:
            for key, value in derived.items():
                reslist.append((key, value["size"], value["mimetype"], value["customData"]))

    except Exception as e:
        logging.error(f"cloudfunction_thumbnailer failed with: {e=}")
    return reslist


class fileBaseSkel(TreeSkel):
    """
        Default file leaf skeleton.
    """
    kindName = "file"

    size = StringBone(
        descr="Size",
        readOnly=True,
        searchable=True
    )

    dlkey = StringBone(
        descr="Download-Key",
        readOnly=True
    )
    name = StringBone(
        descr="Filename",
        caseSensitive=False,
        searchable=True
    )

    mimetype = StringBone(
        descr="Mime-Info",
        readOnly=True
    )

    weak = BooleanBone(
        descr="Weak reference",
        readOnly=True,
        visible=False
    )
    pending = BooleanBone(
        descr="Pending upload",
        readOnly=True,
        visible=False,
        defaultValue=False
    )

    width = NumericBone(
        descr="Width",
        readOnly=True,
        searchable=True
    )

    height = NumericBone(
        descr="Height",
        readOnly=True,
        searchable=True
    )

    downloadUrl = InjectStoreURLBone(
        descr="Download-URL",
        readOnly=True,
        visible=False
    )

    derived = BaseBone(
        descr="Derived Files",
        readOnly=True,
        visible=False
    )

    pendingparententry = KeyBone(
        descr="Pending key Reference",
        readOnly=True,
        visible=False
    )

    def preProcessBlobLocks(self, locks):
        """
            Ensure that our dlkey is locked even if we don't have a filebone here
        """
        if not self["weak"] and self["dlkey"]:
            locks.add(self["dlkey"])
        return locks

    @classmethod
    def refresh(cls, skelValues):
        super().refresh(skelValues)
        if conf.get("viur.viur2import.blobsource"):
            importData = importBlobFromViur2(skelValues["dlkey"], skelValues["name"])
            if importData:
                if not skelValues["downloadUrl"]:
                    skelValues["downloadUrl"] = importData
                skelValues["pendingparententry"] = False


class fileNodeSkel(TreeSkel):
    """
        Default file node skeleton.
    """
    kindName = "file_rootNode"

    name = StringBone(
        descr="Name",
        required=True,
        searchable=True
    )

    rootNode = BooleanBone(
        descr="Is RootNode"
    )


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
        "icon": "icon-file-system"
    }

    blobCacheTime = 60 * 60 * 24  # Requests to file/download will be served with cache-control: public, max-age=blobCacheTime if set

    def write(self, filename: str, content: Any, mimetype: str = "text/plain", width: int = None,
              height: int = None) -> db.Key:
        """
        Write a file from any buffer into the file module.

        :param filename: Filename to be written.
        :param content:  The file content to be written, as bytes-like object.
        :param mimetype: The file's mimetype.
        :param width: Optional width information for the file.
        :param height: Optional height information for the file.

        :return: Returns the key of the file object written. This can be associated e.g. with a FileBone.
        """
        dl_key = utils.generateRandomString()

        blob = bucket.blob("%s/source/%s" % (dl_key, filename))
        blob.upload_from_file(BytesIO(content), content_type=mimetype)

        skel = self.addSkel("leaf")
        skel["name"] = filename
        skel["size"] = blob.size
        skel["mimetype"] = mimetype
        skel["dlkey"] = dl_key
        skel["weak"] = True
        skel["width"] = width
        skel["height"] = height

        return skel.toDB()

    @CallDeferred
    def deleteRecursive(self, parentKey):
        files = db.Query(self.leafSkelCls().kindName).filter("parentdir =", parentKey).iter()
        for fileEntry in files:
            utils.markFileForDeletion(fileEntry["dlkey"])
            skel = self.leafSkelCls()

            if skel.fromDB(str(fileEntry.key())):
                skel.delete()
        dirs = db.Query(self.nodeSkelCls().kindName).filter("parentdir", parentKey).iter()
        for d in dirs:
            self.deleteRecursive(d.key)
            skel = self.nodeSkelCls()
            if skel.fromDB(d.key):
                skel.delete()

    def signUploadURL(self, mimeTypes: Union[List[str], None] = None, maxSize: Union[int, None] = None,
                      node: Union[str, None] = None):
        """
        Internal helper that will create a signed upload-url that can be used to retrieve an uploadURL from
        getUploadURL for guests / users without having file/add permissions. This URL is valid for an hour and can
        be used to upload multiple files.
        :param mimeTypes: A list of valid mimetypes that can be uploaded (wildcards like "image/*" are supported) or
            None (no restriction on filetypes)
        :param maxSize: The maximum filesize in bytes or None for no limit
        :param node: The (string encoded) key of a file-leaf (=directory) where this file will be uploaded into or
            None (the file will then not show up in the filebrowser).
            .. Warning::
                If node is set it's the callers responsibility to ensure node is a valid key and that the user has
                the permission to upload into that directory. ViUR does *not* enforce any canAccess restrictions for
                keys passed to this function!
        :return: authData and authSig for the getUploadURL function below
        """
        dataDict = {
            "validUntil": (datetime.now() + timedelta(hours=1)).strftime("%Y%m%d%H%M"),
            "validMimeTypes": [x.lower() for x in mimeTypes] if mimeTypes else None,
            "maxSize": maxSize,
            "node": node,
        }
        dataStr = base64.b64encode(json.dumps(dataDict).encode("UTF-8"))
        sig = utils.hmacSign(dataStr)
        return dataStr.decode("ASCII"), sig

    def initializeUpload(self,
                         fileName: str,
                         mimeType: str,
                         node: Union[str, None],
                         size: Union[int, None] = None) -> Tuple[str, str]:
        """
        Internal helper that registers a new upload. Will create the pending fileSkel entry (needed to remove any
        started uploads from GCS if that file isn't used) and creates a resumable (and signed) uploadURL for that.
        :param fileName: Name of the file that will be uploaded
        :param mimeType: Mimetype of said file
        :param node: If set (to a string-key representation of a file-node) the upload will be written to this directory
        :param size: The *exact* filesize we're accepting in Bytes. Used to enforce a filesize limit by getUploadURL
        :return: Str-Key of the new file-leaf entry, the signed upload-url
        """
        global bucket
        fileName = sanitizeFileName(fileName)

        targetKey = utils.generateRandomString()
        blob = bucket.blob("%s/source/%s" % (targetKey, fileName))
        uploadUrl = blob.create_resumable_upload_session(content_type=mimeType, size=size, timeout=60)
        # Create a corresponding file-lock object early, otherwise we would have to ensure that the file-lock object
        # the user creates matches the file he had uploaded
        fileSkel = self.addSkel("leaf")
        fileSkel["name"] = "pending"
        fileSkel["size"] = 0
        fileSkel["mimetype"] = "application/octetstream"
        fileSkel["dlkey"] = targetKey
        fileSkel["parentdir"] = None
        fileSkel["pendingparententry"] = db.keyHelper(node, self.addSkel("node").kindName) if node else None
        fileSkel["pending"] = True
        fileSkel["weak"] = True
        fileSkel["width"] = 0
        fileSkel["height"] = 0
        fileSkel.toDB()
        # Mark that entry dirty as we might never receive an add
        utils.markFileForDeletion(targetKey)
        return db.encodeKey(fileSkel["key"]), uploadUrl

    @exposed
    def getUploadURL(self, fileName, mimeType, size=None, skey=None, *args, **kwargs):
        node = kwargs.get("node")
        authData = kwargs.get("authData")
        authSig = kwargs.get("authSig")
        # Validate the the contentType from the client seems legit
        mimeType = mimeType.lower()
        assert len(mimeType.split("/")) == 2, "Invalid Mime-Type"
        assert all([x in string.ascii_letters + string.digits + "/-.+" for x in mimeType]), "Invalid Mime-Type"
        if authData and authSig:
            # First, validate the signature, otherwise we don't need to proceed any further
            if not utils.hmacVerify(authData.encode("ASCII"), authSig):
                raise errors.Forbidden()
            authData = json.loads(base64.b64decode(authData.encode("ASCII")).decode("UTF-8"))
            if datetime.strptime(authData["validUntil"], "%Y%m%d%H%M") < datetime.now():
                raise errors.Gone()
            if authData["validMimeTypes"]:
                for validMimeType in authData["validMimeTypes"]:
                    if validMimeType == mimeType or (
                        validMimeType.endswith("*") and mimeType.startswith(validMimeType[:-1])):
                        break
                else:
                    raise errors.NotAcceptable()
            node = authData["node"]
            maxSize = authData["maxSize"]
        else:
            if node:
                rootNode = self.getRootNode(node)
                if not self.canAdd("leaf", rootNode):
                    raise errors.Forbidden()
            else:
                if not self.canAdd("leaf", None):
                    raise errors.Forbidden()
            maxSize = None  # The user has some file/add permissions, don't restrict fileSize
        if maxSize:
            try:
                size = int(size)
                assert size <= maxSize
            except:  # We have a size-limit set - but no size supplied
                raise errors.PreconditionFailed()
        else:
            size = None

        if not securitykey.validate(skey, useSessionKey=True):
            raise errors.PreconditionFailed()

        targetKey, uploadUrl = self.initializeUpload(fileName, mimeType.lower(), node, size)

        resDict = {
            "uploadUrl": uploadUrl,
            "uploadKey": targetKey,
        }
        if authData and authSig:
            # In this case, we'd have to store the key in the users session so he can call add() later on
            session = utils.currentSession.get()
            if not "pendingFileUploadKeys" in session:
                session["pendingFileUploadKeys"] = []
            session["pendingFileUploadKeys"].append(targetKey)
            # Clamp to the latest 50 pending uploads
            session["pendingFileUploadKeys"] = session["pendingFileUploadKeys"][-50:]
            session.markChanged()
        return self.render.view(resDict)

    @exposed
    def download(self, blobKey: str, fileName: str = "", download: str = "", sig: str = "", *args, **kwargs):
        """
        Download a file.
        :param blobKey: The unique blob key of the file.
        :param fileName: Optional filename to provide in the header.
        :param download: Set header to attachment retrival, set explictly to "1" if download is wanted.
        """
        global credentials, bucket
        if not sig:
            # Check if the current user has the right to download *any* blob present in this application.
            # blobKey is then the path inside cloudstore - not a base64 encoded tuple
            usr = utils.getCurrentUser()
            if not usr:
                raise errors.Unauthorized()
            if "root" not in usr["access"] and "file-view" not in usr["access"]:
                raise errors.Forbidden()
            validUntil = "-1"  # Prevent this from being cached down below
            blob = bucket.get_blob(blobKey)
            downloadFilename = ""
        else:
            # We got an request including a signature (probably a guest or a user without file-view access)
            # First, validate the signature, otherwise we don't need to proceed any further
            if not utils.hmacVerify(blobKey.encode("ASCII"), sig):
                raise errors.Forbidden()
            # Split the blobKey into the individual fields it should contain
            try:
                dlPath, validUntil, downloadFilename = urlsafe_b64decode(blobKey).decode("UTF-8").split("\0")
            except:  # It's the old format, without an downloadFileName
                dlPath, validUntil = urlsafe_b64decode(blobKey).decode("UTF-8").split("\0")
                downloadFilename = ""
            if validUntil != "0" and datetime.strptime(validUntil, "%Y%m%d%H%M") < datetime.now():
                raise errors.Gone()
            blob = bucket.get_blob(dlPath)
        if not blob:
            raise errors.Gone()
        if downloadFilename:
            contentDisposition = "attachment; filename=%s" % downloadFilename
        elif download:
            fileName = sanitizeFileName(blob.name.split("/")[-1])
            contentDisposition = "attachment; filename=%s" % fileName
        else:
            fileName = sanitizeFileName(blob.name.split("/")[-1])
            contentDisposition = "filename=%s" % fileName
        if isinstance(credentials, ServiceAccountCredentials):  # We run locally with an service-account.json
            expiresAt = datetime.now() + timedelta(seconds=60)
            signedUrl = blob.generate_signed_url(expiresAt, response_disposition=contentDisposition, version="v4")
            raise errors.Redirect(signedUrl)
        elif conf["viur.instance.is_dev_server"]:  # No Service-Account to sign with - Serve everything directly
            response = utils.currentRequest.get().response
            response.headers["Content-Type"] = blob.content_type
            if contentDisposition:
                response.headers["Content-Disposition"] = contentDisposition
            return blob.download_as_bytes()
        else:  # We are inside the appengine
            if validUntil == "0":  # Its an indefinitely valid URL
                if blob.size < 5 * 1024 * 1024:  # Less than 5 MB - Serve directly and push it into the ede caches
                    response = utils.currentRequest.get().response
                    response.headers["Content-Type"] = blob.content_type
                    response.headers["Cache-Control"] = "public, max-age=604800"  # 7 Days
                    if contentDisposition:
                        response.headers["Content-Disposition"] = contentDisposition
                    return blob.download_as_bytes()
            # Default fallback - create a signed URL and redirect
            authRequest = requests.Request()
            expiresAt = datetime.now() + timedelta(seconds=60)
            signing_credentials = compute_engine.IDTokenCredentials(authRequest, "")
            signedUrl = blob.generate_signed_url(
                expiresAt,
                credentials=signing_credentials,
                response_disposition=contentDisposition,
                version="v4")
            raise errors.Redirect(signedUrl)

    @exposed
    @forceSSL
    @forcePost
    def add(self, skelType: SkelType, node=None, *args, **kwargs):
        ## We can't add files directly (they need to be uploaded
        # if skelType != "node":
        #    raise errors.NotAcceptable()
        if skelType == "leaf":  # We need to handle leafs separately here
            skey = kwargs.get("skey")
            targetKey = kwargs.get("key")
            if not skey or not securitykey.validate(skey, useSessionKey=True) or not targetKey:
                raise errors.PreconditionFailed()
            skel = self.addSkel("leaf")
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
                # Check for a marker in this session (created if using a signed upload URL)
                session = utils.currentSession.get()
                if targetKey not in (session.get("pendingFileUploadKeys") or []):
                    raise errors.Forbidden()
                session["pendingFileUploadKeys"].remove(targetKey)
                session.markChanged()
            blobs = list(bucket.list_blobs(prefix="%s/" % skel["dlkey"]))
            if len(blobs) != 1:
                logging.error("Invalid number of blobs in folder")
                logging.error(targetKey)
                raise errors.PreconditionFailed()
            blob = blobs[0]
            skel["mimetype"] = utils.escapeString(blob.content_type)
            if any([x in blob.name for x in "$<>'\""]):  # Prevent these Characters from being used in a fileName
                raise errors.PreconditionFailed()
            skel["name"] = utils.escapeString(blob.name.replace("%s/source/" % skel["dlkey"], ""))
            skel["size"] = blob.size
            skel["parentrepo"] = rootNode["key"] if rootNode else None
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


@CallDeferred
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


@CallDeferred
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
