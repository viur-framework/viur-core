import base64
import datetime
import google.auth
import google.oauth2
import hashlib
import hmac
import html
import io
import json
import logging
import PIL
import requests
import string
import typing as t
from urllib.parse import quote as urlquote
from urllib.request import urlopen
from google.cloud import storage
from viur.core import conf, current, db, errors, utils
from viur.core.bones import BaseBone, BooleanBone, KeyBone, NumericBone, StringBone
from viur.core.decorators import *
from viur.core.prototypes.tree import SkelType, Tree, TreeSkel
from viur.core.skeleton import SkeletonInstance, skeletonByKind
from viur.core.tasks import CallDeferred, DeleteEntitiesIter, PeriodicTask


# Globals for connectivity

_credentials, __project_id = google.auth.default()
client = storage.Client(__project_id, _credentials)
bucket = client.lookup_bucket(f"""{__project_id}.appspot.com""")


# Helper functions currently resist here

def sanitize_filename(filename: str) -> str:
    """
        Sanitize the filename so it can be safely downloaded or be embedded into html
    """
    filename = filename[:100]  # Limit to 100 Chars max
    filename = "".join(ch for ch in filename if ch not in "\0'\"<>\n;$&?#:;/\\")  # Remove invalid Chars
    filename = filename.strip(".")  # Ensure the filename does not start or end with a dot
    filename = urlquote(filename)  # Finally quote any non-ASCII characters
    return filename


def hmac_sign(data: t.Any) -> str:
    assert conf.file_hmac_key is not None, "No hmac-key set!"
    if not isinstance(data, bytes):
        data = str(data).encode("UTF-8")
    return hmac.new(conf.file_hmac_key, msg=data, digestmod=hashlib.sha3_384).hexdigest()


def hmac_verify(data: t.Any, signature: str) -> bool:
    return hmac.compare_digest(hmac_sign(data.encode("ASCII")), signature)


def create_download_url(
    dlkey: str,
    fileName: str,
    derived: bool = False,
    expires: t.Optional[datetime.timedelta] = datetime.timedelta(hours=1),
    downloadFileName: t.Optional[str] = None
) -> str:
    """
        Utility function that creates a signed download-url for the given folder/filename combination

        :param folder: The GCS-Folder (= the download-key) for that file
        :param fileName: The name of that file. Either the original filename as uploaded or the name of a dervived file
        :param derived: True, if it points to a derived file, False if it points to the original uploaded file
        :param expires:
            None if the file is supposed to be public (which causes it to be cached on the google ede caches),
            otherwise a datetime.timedelta of how long that link should be valid
        :param downloadFileName: If set, we'll force to browser to download this blob with the given filename
        :return: THe signed download-url relative to the current domain (eg /download/...)
    """
    # Undo escaping on ()= performed on fileNames
    fileName = fileName.replace("&#040;", "(").replace("&#041;", ")").replace("&#061;", "=")
    if derived:
        filePath = f"{dlkey}/derived/{fileName}"
    else:
        filePath = f"{dlkey}/source/{fileName}"
    if downloadFileName:
        downloadFileName = sanitize_filename(downloadFileName)
    else:
        downloadFileName = ""
    expires = ((datetime.datetime.now() + expires).strftime("%Y%m%d%H%M") if expires else 0)
    sigStr = f"{filePath}\0{expires}\0{downloadFileName}"
    sigStr = base64.urlsafe_b64encode(sigStr.encode("UTF-8"))
    resstr = hmac_sign(sigStr)
    return f"""/file/download/{sigStr.decode("ASCII")}?sig={resstr}"""


def create_src_set(
    self,
    fileObj: dict,
    expires: t.Optional[datetime.timedelta] = datetime.timedelta(hours=1),
    width: t.Optional[int] = None,
    height: t.Optional[int] = None
) -> str:
    """
        Generates a string suitable for use as the srcset tag in html. This functionality provides the browser
        with a list of images in different sizes and allows it to choose the smallest file that will fill it's viewport
        without upscaling.

        :param fileObj: The file-bone (or if multiple=True a single value from it) to generate the srcset.
        :param expires:
            None if the file is supposed to be public (which causes it to be cached on the google edecaches), otherwise
            it's lifetime in seconds
        :param width:
            A list of widths that should be included in the srcset.
            If a given width is not available, it will be skipped.
        :param height: A list of heights that should be included in the srcset. If a given height is not available,
            it will be skipped.
        :return: The srctag generated or an empty string if a invalid file object was supplied
    """
    if not width and not height:
        logging.error("Neither width or height supplied")
        return ""

    if "dlkey" not in fileObj and "dest" in fileObj:
        fileObj = fileObj["dest"]

    if expires:
        expires = datetime.timedelta(minutes=expires)

    from viur.core.skeleton import SkeletonInstance  # avoid circular imports

    if not (
        isinstance(fileObj, (SkeletonInstance, dict))
        and "dlkey" in fileObj
        and "derived" in fileObj
    ):
        logging.error("Invalid fileObj supplied")
        return ""

    if not isinstance(fileObj["derived"], dict):
        logging.error("No derives available")
        return ""

    resList = []
    for fileName, derivate in fileObj["derived"]["files"].items():
        customData = derivate.get("customData", {})

        if width and customData.get("width") in width:
            resList.append(
                f"""{create_download_url(fileObj["dlkey"], fileName, True, expires)} {customData["width"]}w"""
            )

        if height and customData.get("height") in height:
            resList.append(
                f"""{create_download_url(fileObj["dlkey"], fileName, True, expires)} {customData["height"]}h"""
            )

    return ", ".join(resList)


def importBlobFromViur2(dlKey, fileName):
    if not conf.viur2import_blobsource:
        return False
    existingImport = db.Get(db.Key("viur-viur2-blobimport", dlKey))
    if existingImport:
        if existingImport["success"]:
            return existingImport["dlurl"]
        return False
    if conf.viur2import_blobsource["infoURL"]:
        try:
            importDataReq = urlopen(conf.viur2import_blobsource["infoURL"] + dlKey)
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
        oldBlobName = conf.viur2import_blobsource["gsdir"] + "/" + importData["key"]
        srcBlob = storage.Blob(bucket=bucket,
                               name=conf.viur2import_blobsource["gsdir"] + "/" + importData["key"])
    else:
        oldBlobName = conf.viur2import_blobsource["gsdir"] + "/" + dlKey
        srcBlob = storage.Blob(bucket=bucket, name=conf.viur2import_blobsource["gsdir"] + "/" + dlKey)
    if not srcBlob.exists():
        marker = db.Entity(db.Key("viur-viur2-blobimport", dlKey))
        marker["success"] = False
        marker["error"] = "Local SRC-Blob missing"
        marker["oldBlobName"] = oldBlobName
        db.Put(marker)
        return False
    bucket.rename_blob(srcBlob, f"{dlKey}/source/{fileName}")
    marker = db.Entity(db.Key("viur-viur2-blobimport", dlKey))
    marker["success"] = True
    marker["old_src_key"] = dlKey
    marker["old_src_name"] = fileName
    marker["dlurl"] = create_download_url(dlKey, fileName, False, None)
    db.Put(marker)
    return marker["dlurl"]


def thumbnailer(fileSkel, existingFiles, params):
    file_name = html.unescape(fileSkel["name"])
    blob = bucket.get_blob(f"""{fileSkel["dlkey"]}/source/{file_name}""")
    if not blob:
        logging.warning(f"""Blob {fileSkel["dlkey"]}/source/{file_name} is missing from cloud storage!""")
        return
    fileData = io.BytesIO()
    blob.download_to_file(fileData)
    resList = []
    for sizeDict in params:
        fileData.seek(0)
        outData = io.BytesIO()
        try:
            img = PIL.Image.open(fileData)
        except PIL.Image.UnidentifiedImageError:  # Can't load this image; so there's no need to try other resolutions
            return []
        iccProfile = img.info.get('icc_profile')
        if iccProfile:
            # JPEGs might be encoded with a non-standard color-profile; we need to compensate for this if we convert
            # to WEBp as we'll loose this color-profile information
            f = io.BytesIO(iccProfile)
            src_profile = PIL.ImageCms.ImageCmsProfile(f)
            dst_profile = PIL.ImageCms.createProfile('sRGB')
            try:
                img = PIL.ImageCms.profileToProfile(
                    img,
                    inputProfile=src_profile,
                    outputProfile=dst_profile,
                    outputMode="RGBA" if img.has_transparency_data else "RGB")
            except Exception as e:
                logging.exception(e)
                continue
        fileExtension = sizeDict.get("fileExtension", "webp")
        if "width" in sizeDict and "height" in sizeDict:
            width = sizeDict["width"]
            height = sizeDict["height"]
            targetName = f"thumbnail-{width}-{height}.{fileExtension}"
        elif "width" in sizeDict:
            width = sizeDict["width"]
            height = int((float(img.size[1]) * float(width / float(img.size[0]))))
            targetName = f"thumbnail-w{width}.{fileExtension}"
        else:  # No default fallback - ignore
            continue
        mimeType = sizeDict.get("mimeType", "image/webp")
        img = img.resize((width, height), PIL.Image.LANCZOS)
        img.save(outData, fileExtension)
        outSize = outData.tell()
        outData.seek(0)
        targetBlob = bucket.blob(f"""{fileSkel["dlkey"]}/derived/{targetName}""")
        targetBlob.upload_from_file(outData, content_type=mimeType)
        resList.append((targetName, outSize, mimeType, {"mimetype": mimeType, "width": width, "height": height}))
    return resList


def cloudfunction_thumbnailer(fileSkel, existingFiles, params):
    """External Thumbnailer for images.

    The corresponding cloudfunction can be found here .
    https://github.com/viur-framework/viur-cloudfunctions/tree/main/thumbnailer

    You can use it like so:
    main.py:

    .. code-block:: python

        from viur.core.modules.file import cloudfunction_thumbnailer

        conf.file_thumbnailer_url = "https://xxxxx.cloudfunctions.net/imagerenderer"
        conf.file_derivations = {"thumbnail": cloudfunction_thumbnailer}

        conf.derives_pdf = {
            "thumbnail": [{"width": 1920,"sites":"1,2"}]
        }

    skeletons/xxx.py:
    .. code-block:: python

        test = FileBone(derive=conf.derives_pdf)
   """

    if not conf.file_thumbnailer_url:
        raise ValueError("conf.file_thumbnailer_url is not set")

    def getsignedurl():
        if conf.instance.is_dev_server:
            signedUrl = create_download_url(fileSkel["dlkey"], fileSkel["name"])
        else:
            path = f"""{fileSkel["dlkey"]}/source/{file_name}"""
            if not (blob := bucket.get_blob(path)):
                logging.warning(f"Blob {path} is missing from cloud storage!")
                return None
            authRequest = google.auth.transport.requests.Request()
            expiresAt = datetime.datetime.now() + datetime.timedelta(seconds=60)
            signing_credentials = google.auth.compute_engine.IDTokenCredentials(authRequest, "")
            contentDisposition = f"""filename={fileSkel["name"]}"""
            signedUrl = blob.generate_signed_url(
                expiresAt,
                credentials=signing_credentials,
                response_disposition=contentDisposition,
                version="v4")
        return signedUrl

    def make_request():
        headers = {"Content-Type": "application/json"}
        data_str = base64.b64encode(json.dumps(dataDict).encode("UTF-8"))
        sig = hmac_sign(data_str)
        datadump = json.dumps({"dataStr": data_str.decode('ASCII'), "sign": sig})
        resp = requests.post(conf.file_thumbnailer_url, data=datadump, headers=headers, allow_redirects=False)
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
        "baseUrl": current.request.get().request.host_url.lower(),
        "targetKey": fileSkel["dlkey"],
        "nameOnly": True
    }
    if not (derivedData := make_request()):
        return

    uploadUrls = {}
    for data in derivedData["values"]:
        fileName = sanitize_filename(data["name"])
        blob = bucket.blob(f"""{fileSkel["dlkey"]}/derived/{fileName}""")
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


class DownloadUrlBone(BaseBone):
    """
    This bone is used to inject a freshly signed download url into a FileSkel.
    """

    def unserialize(self, skel, name):
        if "dlkey" in skel.dbEntity and "name" in skel.dbEntity:
            skel.accessedValues[name] = create_download_url(
                skel["dlkey"], skel["name"], expires=conf.render_json_download_url_expiration
            )
            return True
        return False


class FileLeafSkel(TreeSkel):
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

    downloadUrl = DownloadUrlBone(
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
        if conf.viur2import_blobsource:
            importData = importBlobFromViur2(skelValues["dlkey"], skelValues["name"])
            if importData:
                if not skelValues["downloadUrl"]:
                    skelValues["downloadUrl"] = importData
                skelValues["pendingparententry"] = False


class FileNodeSkel(TreeSkel):
    """
        Default file node skeleton.
    """
    kindName = "file_rootNode"  # FIXME: VIUR4, don't use "_rootNode" kindname

    name = StringBone(
        descr="Name",
        required=True,
        searchable=True
    )

    rootNode = BooleanBone(
        descr="Is RootNode",
        defaultValue=False,
    )


class File(Tree):
    leafSkelCls = FileLeafSkel
    nodeSkelCls = FileNodeSkel

    handler = "tree.simple.file"
    adminInfo = {
        "icon": "file-system",
        "handler": handler,  # fixme: Use static handler; Remove with VIUR4!
    }

    roles = {
        "*": "view",
        "editor": ("add", "edit"),
        "admin": "*",
    }

    def write(self, filename: str, content: t.Any, mimetype: str = "text/plain", width: int = None,
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
        dl_key = utils.string.random()

        blob = bucket.blob(f"{dl_key}/source/{filename}")
        blob.upload_from_file(io.BytesIO(content), content_type=mimetype)

        skel = self.addSkel("leaf")
        skel["name"] = filename
        skel["size"] = blob.size
        skel["mimetype"] = mimetype
        skel["dlkey"] = dl_key
        skel["weak"] = True
        skel["width"] = width
        skel["height"] = height

        return skel.toDB()

    def read(self, key: db.Key | int | str | None = None, path: str | None = None) -> tuple[io.BytesIO, str]:
        """
        Read a file from the Cloud Storage.

        If a key and a path are provided, the key is preferred.
        This means that the entry in the db is searched first and if this is not found, the path is used.

        :param key: Key of the LeafSkel that contains the "dlkey" and the "name".
        :param path: The path of the file in the Cloud Storage Bucket.

        :return: Returns the file as a io.BytesIO buffer and the content-type
        """
        if not key and not path:
            raise ValueError("Please provide a key or a path")
        if key:
            skel = self.viewSkel("leaf")
            if not skel.fromDB(db.keyHelper(key, skel.kindName)):
                if not path:
                    raise ValueError("This skeleton is not in the database!")
            else:
                path = f"""{skel["dlkey"]}/source/{skel["name"]}"""

        blob = bucket.blob(path)
        return io.BytesIO(blob.download_as_bytes()), blob.content_type

    @CallDeferred
    def deleteRecursive(self, parentKey):
        files = db.Query(self.leafSkelCls().kindName).filter("parentdir =", parentKey).iter()
        for fileEntry in files:
            self.mark_for_deletion(fileEntry["dlkey"])
            skel = self.leafSkelCls()

            if skel.fromDB(str(fileEntry.key())):
                skel.delete()
        dirs = db.Query(self.nodeSkelCls().kindName).filter("parentdir", parentKey).iter()
        for d in dirs:
            self.deleteRecursive(d.key)
            skel = self.nodeSkelCls()
            if skel.fromDB(d.key):
                skel.delete()

    def initializeUpload(self,
                         fileName: str,
                         mimeType: str,
                         node: str | None,
                         size: int | None = None) -> tuple[str, str]:
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
        fileName = sanitize_filename(fileName)

        targetKey = utils.string.random()
        blob = bucket.blob(f"{targetKey}/source/{fileName}")
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
        self.mark_for_deletion(targetKey)
        return db.encodeKey(fileSkel["key"]), uploadUrl

    @exposed
    @skey
    def getUploadURL(self, fileName: str, mimeType: str, size: int = None, *args, **kwargs):
        node = kwargs.get("node")
        authData = kwargs.get("authData")
        authSig = kwargs.get("authSig")

        # Validate the contentType from the client seems legit
        mimeType = mimeType.strip().lower()
        if not (
            mimeType
            and mimeType.count("/") == 1
            and all(ch in string.ascii_letters + string.digits + "/-.+" for ch in mimeType)
        ):
            raise errors.UnprocessableEntity(f"Invalid mime-type {mimeType} provided")

        if authData and authSig:
            # First, validate the signature, otherwise we don't need to proceed further
            if not hmac_verify(authData, authSig):
                raise errors.Unauthorized()

            authData = json.loads(base64.b64decode(authData.encode("ASCII")).decode("UTF-8"))

            if datetime.datetime.strptime(authData["validUntil"], "%Y%m%d%H%M") < datetime.datetime.now():
                raise errors.Gone("The upload URL has expired")

            if authData["validMimeTypes"]:
                for validMimeType in authData["validMimeTypes"]:
                    if validMimeType == mimeType or (
                        validMimeType.endswith("*") and mimeType.startswith(validMimeType[:-1])):
                        break
                else:
                    raise errors.UnprocessableEntity(f"Invalid mime-type {mimeType} provided")

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
            if size > maxSize:
                raise errors.UnprocessableEntity(f"Size {size} exceeds maximum size {maxSize}")
        else:
            size = None

        targetKey, uploadUrl = self.initializeUpload(fileName, mimeType, node, size)

        resDict = {
            "uploadUrl": uploadUrl,
            "uploadKey": targetKey,
        }

        if authData and authSig:
            # In this case, we'd have to store the key in the users session so he can call add() later on
            session = current.session.get()
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
        global _credentials, bucket
        if not sig:
            # Check if the current user has the right to download *any* blob present in this application.
            # blobKey is then the path inside cloudstore - not a base64 encoded tuple
            if not (usr := current.user.get()):
                raise errors.Unauthorized()
            if "root" not in usr["access"] and "file-view" not in usr["access"]:
                raise errors.Forbidden()
            validUntil = "-1"  # Prevent this from being cached down below
            blob = bucket.get_blob(blobKey)
            downloadFilename = ""
        else:
            # We got an request including a signature (probably a guest or a user without file-view access)
            # First, validate the signature, otherwise we don't need to proceed any further
            if not hmac_verify(blobKey, sig):
                raise errors.Forbidden()
            # Split the blobKey into the individual fields it should contain
            try:
                dlPath, validUntil, downloadFilename = base64.urlsafe_b64decode(blobKey).decode("UTF-8").split("\0")
            except:  # It's the old format, without an downloadFileName
                dlPath, validUntil = base64.urlsafe_b64decode(blobKey).decode("UTF-8").split("\0")
                downloadFilename = ""
            if validUntil != "0" and datetime.datetime.strptime(validUntil, "%Y%m%d%H%M") < datetime.datetime.now():
                raise errors.Gone()
            blob = bucket.get_blob(dlPath)
        if not blob:
            raise errors.Gone()
        if downloadFilename:
            contentDisposition = f"attachment; filename={downloadFilename}"
        elif download:
            fileName = sanitize_filename(blob.name.split("/")[-1])
            contentDisposition = f"attachment; filename={fileName}"
        else:
            fileName = sanitize_filename(blob.name.split("/")[-1])
            contentDisposition = f"filename={fileName}"
        if isinstance(_credentials, ServiceAccountCredentials):
            expiresAt = datetime.datetime.now() + datetime.timedelta(seconds=60)
            signedUrl = blob.generate_signed_url(expiresAt, response_disposition=contentDisposition, version="v4")
            raise errors.Redirect(signedUrl)
        elif conf.instance.is_dev_server:  # No Service-Account to sign with - Serve everything directly
            response = current.request.get().response
            response.headers["Content-Type"] = blob.content_type
            if contentDisposition:
                response.headers["Content-Disposition"] = contentDisposition
            return blob.download_as_bytes()
        else:  # We are inside the appengine
            if validUntil == "0":  # Its an indefinitely valid URL
                if blob.size < 5 * 1024 * 1024:  # Less than 5 MB - Serve directly and push it into the ede caches
                    response = current.request.get().response
                    response.headers["Content-Type"] = blob.content_type
                    response.headers["Cache-Control"] = "public, max-age=604800"  # 7 Days
                    if contentDisposition:
                        response.headers["Content-Disposition"] = contentDisposition
                    return blob.download_as_bytes()
            # Default fallback - create a signed URL and redirect
            authRequest = google.auth.transport.requests.Request()
            expiresAt = datetime.datetime.now() + datetime.timedelta(seconds=60)
            signing_credentials = google.auth.compute_engine.IDTokenCredentials(authRequest, "")
            signedUrl = blob.generate_signed_url(
                expiresAt,
                credentials=signing_credentials,
                response_disposition=contentDisposition,
                version="v4")
            raise errors.Redirect(signedUrl)

    @exposed
    @force_ssl
    @force_post
    @skey(allow_empty=True)
    def add(self, skelType: SkelType, node: db.Key | int | str | None = None, *args, **kwargs):
        ## We can't add files directly (they need to be uploaded
        # if skelType != "node":
        #    raise errors.NotAcceptable()
        if skelType == "leaf":  # We need to handle leafs separately here
            targetKey = kwargs.get("key")
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
                session = current.session.get()
                if targetKey not in (session.get("pendingFileUploadKeys") or []):
                    raise errors.Forbidden()
                session["pendingFileUploadKeys"].remove(targetKey)
                session.markChanged()
            blobs = list(bucket.list_blobs(prefix=f"""{skel["dlkey"]}/"""))
            if len(blobs) != 1:
                logging.error("Invalid number of blobs in folder")
                logging.error(targetKey)
                raise errors.PreconditionFailed()
            blob = blobs[0]
            skel["mimetype"] = utils.string.escape(blob.content_type)
            if any([x in blob.name for x in "$<>'\""]):  # Prevent these Characters from being used in a fileName
                raise errors.PreconditionFailed()
            skel["name"] = utils.string.escape(blob.name.replace(f"""{skel["dlkey"]}/source/""", ""))
            skel["size"] = blob.size
            skel["parentrepo"] = rootNode["key"] if rootNode else None
            skel["weak"] = rootNode is None
            skel.toDB()
            # Add updated download-URL as the auto-generated isn't valid yet
            skel["downloadUrl"] = create_download_url(skel["dlkey"], skel["name"])
            return self.render.addSuccess(skel)

        return super().add(skelType, node, *args, **kwargs)

    def onEdit(self, skelType: SkelType, skel: SkeletonInstance):
        super().onEdit(skelType, skel)
        old_skel = self.editSkel(skelType)
        old_skel.setEntity(skel.dbEntity)

        if old_skel["name"] == skel["name"]:  # name not changed we can return
            return
        # Move Blob to new name
        # https://cloud.google.com/storage/docs/copying-renaming-moving-objects
        old_path = f"{skel['dlkey']}/source/{html.unescape(old_skel['name'])}"
        new_path = f"{skel['dlkey']}/source/{html.unescape(skel['name'])}"
        old_blob = bucket.get_blob(old_path)
        if not old_blob:
            raise errors.Gone()
        bucket.copy_blob(old_blob, bucket, new_path, if_generation_match=0)
        bucket.delete_blob(old_path)

    def onItemUploaded(self, skel):
        pass

    def mark_for_deletion(self, dlkey: str) -> None:
        """
        Adds a marker to the datastore that the file specified as *dlkey* can be deleted.

        Once the mark has been set, the data store is checked four times (default: every 4 hours)
        if the file is in use somewhere. If it is still in use, the mark goes away, otherwise
        the mark and the file are removed from the datastore. These delayed checks are necessary
        due to database inconsistency.

        :param dlkey: Unique download-key of the file that shall be marked for deletion.
        """
        fileObj = db.Query("viur-deleted-files").filter("dlkey", dlkey).getEntry()

        if fileObj:  # Its allready marked
            return

        fileObj = db.Entity(db.Key("viur-deleted-files"))
        fileObj["itercount"] = 0
        fileObj["dlkey"] = str(dlkey)

        db.Put(fileObj)


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
                logging.info(f"Stale blob is still referenced, {blobKey}")
                continue
            # Add a marker and schedule it for deletion
            fileObj = db.Query("viur-deleted-files").filter("dlkey", blobKey).getEntry()
            if fileObj:  # Its already marked
                logging.info(f"Stale blob already marked for deletion, {blobKey}")
                return
            fileObj = db.Entity(db.Key("viur-deleted-files"))
            fileObj["itercount"] = 0
            fileObj["dlkey"] = str(blobKey)
            logging.info(f"Stale blob marked dirty, {blobKey}")
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
            logging.info(f"""is referenced, {file["dlkey"]}""")
            db.Delete(file.key)
        else:
            if file["itercount"] > maxIterCount:
                logging.info(f"""Finally deleting, {file["dlkey"]}""")
                blobs = bucket.list_blobs(prefix=f"""{file["dlkey"]}/""")
                for blob in blobs:
                    blob.delete()
                db.Delete(file.key)
                # There should be exactly 1 or 0 of these
                for f in skeletonByKind("file")().all().filter("dlkey =", file["dlkey"]).fetch(99):
                    f.delete()
            else:
                logging.debug(f"""Increasing count, {file["dlkey"]}""")
                file["itercount"] += 1
                db.Put(file)
    newCursor = query.getCursor()
    if newCursor:
        doCleanupDeletedFiles(newCursor)


@PeriodicTask(60 * 4)
def start_delete_pending_files():
    """
    Start deletion of pending FileSkels that are older than 7 days.
    """
    DeleteEntitiesIter.startIterOnQuery(
        FileLeafSkel().all()
        .filter("pending =", True)
        .filter("creationdate <", utils.utcNow() - datetime.timedelta(days=7))
    )
