import base64
import datetime
import google.auth
import hashlib
import hmac
import html
import io
import json
import logging
import PIL
import PIL.ImageCms
import re
import requests
import string
import typing as t
import warnings
from collections import namedtuple
from google.appengine.api import images, blobstore
from urllib.parse import quote as urlquote, urlencode
from urllib.request import urlopen

from google.cloud import storage
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from viur.core import conf, current, db, errors, utils
from viur.core.bones import BaseBone, BooleanBone, KeyBone, NumericBone, StringBone
from viur.core.decorators import *
from viur.core.i18n import LanguageWrapper
from viur.core.prototypes.tree import SkelType, Tree, TreeSkel
from viur.core.skeleton import SkeletonInstance, skeletonByKind
from viur.core.tasks import CallDeferred, DeleteEntitiesIter, PeriodicTask


# Globals for connectivity

VALID_FILENAME_REGEX = re.compile(
    # ||   MAY NOT BE THE NAME                  | MADE OF SPECIAL CHARS  |     SPECIAL CHARS + `. `|`
    r"^(?!^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$)[^\x00-\x1F<>:\"\/\\|?*]*[^\x00-\x1F<>:\"\/\\|?*. ]$",
    re.IGNORECASE
)

_CREDENTIALS, _PROJECT_ID = google.auth.default()
GOOGLE_STORAGE_CLIENT = storage.Client(_PROJECT_ID, _CREDENTIALS)

PRIVATE_BUCKET_NAME = f"""{_PROJECT_ID}.appspot.com"""
PUBLIC_BUCKET_NAME = f"""public-dot-{_PROJECT_ID}"""
PUBLIC_DLKEY_SUFFIX = "_pub"

_private_bucket = GOOGLE_STORAGE_CLIENT.lookup_bucket(PRIVATE_BUCKET_NAME)
_public_bucket = None

# FilePath is a descriptor for ViUR file components
FilePath = namedtuple("FilePath", ("dlkey", "is_derived", "filename"))


def importBlobFromViur2(dlKey, fileName):
    bucket = File.get_bucket(dlKey)

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
        except Exception as e:
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
    marker["dlurl"] = File.create_download_url(dlKey, fileName, False, None)
    db.Put(marker)
    return marker["dlurl"]


def thumbnailer(fileSkel, existingFiles, params):
    file_name = html.unescape(fileSkel["name"])
    bucket = File.get_bucket(fileSkel["dlkey"])
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

    bucket = File.get_bucket(fileSkel["dlkey"])

    def getsignedurl():
        if conf.instance.is_dev_server:
            signedUrl = File.create_download_url(fileSkel["dlkey"], fileSkel["name"])
        else:
            path = f"""{fileSkel["dlkey"]}/source/{file_name}"""
            if not (blob := bucket.get_blob(path)):
                logging.warning(f"Blob {path} is missing from cloud storage!")
                return None
            authRequest = google.auth.transport.requests.Request()
            expiresAt = datetime.datetime.now() + datetime.timedelta(seconds=60)
            signing_credentials = google.auth.compute_engine.IDTokenCredentials(authRequest, "")
            content_disposition = f"""filename={fileSkel["name"]}"""
            signedUrl = blob.generate_signed_url(
                expiresAt,
                credentials=signing_credentials,
                response_disposition=content_disposition,
                version="v4")
        return signedUrl

    def make_request():
        headers = {"Content-Type": "application/json"}
        data_str = base64.b64encode(json.dumps(dataDict).encode("UTF-8"))
        sig = File.hmac_sign(data_str)
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
        fileName = File.sanitize_filename(data["name"])
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
            skel.accessedValues[name] = File.create_download_url(
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
        searchable=True,
    )

    dlkey = StringBone(
        descr="Download-Key",
        readOnly=True,
    )

    name = StringBone(
        descr="Filename",
        caseSensitive=False,
        searchable=True,
        vfunc=lambda val: None if File.is_valid_filename(val) else "Invalid filename provided",
    )

    mimetype = StringBone(
        descr="MIME-Type",
        readOnly=True,
    )

    weak = BooleanBone(
        descr="Weak reference",
        readOnly=True,
        visible=False,
    )

    pending = BooleanBone(
        descr="Pending upload",
        readOnly=True,
        visible=False,
        defaultValue=False,
    )

    width = NumericBone(
        descr="Width",
        readOnly=True,
        searchable=True,
    )

    height = NumericBone(
        descr="Height",
        readOnly=True,
        searchable=True,
    )

    downloadUrl = DownloadUrlBone(
        descr="Download-URL",
        readOnly=True,
        visible=False,
    )

    derived = BaseBone(
        descr="Derived Files",
        readOnly=True,
        visible=False,
    )

    pendingparententry = KeyBone(
        descr="Pending key Reference",
        readOnly=True,
        visible=False,
    )

    crc32c_checksum = StringBone(
        descr="CRC32C checksum",
        readOnly=True,
    )

    md5_checksum = StringBone(
        descr="MD5 checksum",
        readOnly=True,
    )

    public = BooleanBone(
        descr="Public File",
        readOnly=True,
        defaultValue=False,
    )

    serving_url = StringBone(
        descr="Serving-URL",
        readOnly=True,
        params={
            "tooltip": "The 'serving_url' is only available in public file repositories.",
        }
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
                skelValues["pendingparententry"] = None

        conf.main_app.file.inject_serving_url(skelValues)


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
    PENDING_POSTFIX = " (pending)"
    DOWNLOAD_URL_PREFIX = "/file/download/"
    INTERNAL_SERVING_URL_PREFIX = "/file/serve/"
    MAX_FILENAME_LEN = 256

    leafSkelCls = FileLeafSkel
    nodeSkelCls = FileNodeSkel

    handler = "tree.simple.file"
    adminInfo = {
        "icon": "folder-fill",
        "handler": handler,  # fixme: Use static handler; Remove with VIUR4!
    }

    roles = {
        "*": "view",
        "editor": ("add", "edit"),
        "admin": "*",
    }

    default_order = "name"

    # Helper functions currently resist here

    @staticmethod
    def get_bucket(dlkey: str) -> google.cloud.storage.bucket.Bucket:
        """
        Retrieves a Google Cloud Storage bucket for the given dlkey.
        """
        global _public_bucket
        if dlkey and dlkey.endswith(PUBLIC_DLKEY_SUFFIX):
            if _public_bucket or (_public_bucket := GOOGLE_STORAGE_CLIENT.lookup_bucket(PUBLIC_BUCKET_NAME)):
                return _public_bucket

            raise ValueError(
                f"""The bucket 'public-dot-{_PROJECT_ID}' does not exist! Please create it with ACL access."""
            )

        return _private_bucket

    @staticmethod
    def is_valid_filename(filename: str) -> bool:
        """
        Verifies a valid filename.

        The filename should be valid on Linux, Mac OS and Windows.
        It should not be longer than MAX_FILENAME_LEN chars.

        Rule set: https://stackoverflow.com/a/31976060/3749896
        Regex test: https://regex101.com/r/iBYpoC/1
        """
        if len(filename) > File.MAX_FILENAME_LEN:
            return False

        return bool(re.match(VALID_FILENAME_REGEX, filename))

    @staticmethod
    def hmac_sign(data: t.Any) -> str:
        assert conf.file_hmac_key is not None, "No hmac-key set!"
        if not isinstance(data, bytes):
            data = str(data).encode("UTF-8")
        return hmac.new(conf.file_hmac_key, msg=data, digestmod=hashlib.sha3_384).hexdigest()

    @staticmethod
    def hmac_verify(data: t.Any, signature: str) -> bool:
        return hmac.compare_digest(File.hmac_sign(data.encode("ASCII")), signature)

    @staticmethod
    def create_internal_serving_url(
        serving_url: str,
        size: int = 0,
        filename: str = "",
        options: str = "",
        download: bool = False
    ) -> str:
        """
        Helper function to generate an internal serving url (endpoint: /file/serve) from a Google serving url.

        This is needed to hide requests to Google as they are internally be routed, and can be the result of a
        legal requirement like GDPR.

        :param serving_url: Is the original serving URL as generated from inject_serving_url()
        :param size: Optional size setting
        :param filename: Optonal filename setting
        :param options: Additional options parameter-pass through to /file/serve
        :param download: Download parameter-pass through to /file/serve
        """

        # Split a serving URL into its components, used by serve function.
        res = re.match(
            r"^https:\/\/(.*?)\.googleusercontent\.com\/(.*?)$",
            serving_url
        )

        if not res:
            raise ValueError(f"Invalid {serving_url=!r} provided")

        # Create internal serving URL
        serving_url = File.INTERNAL_SERVING_URL_PREFIX + "/".join(res.groups())

        # Append additional parameters
        if params := {
                k: v for k, v in {
                    "download": download,
                    "filename": filename,
                    "options": options,
                    "size": size,
                }.items() if v
        }:
            serving_url += f"?{urlencode(params)}"

        return serving_url

    @staticmethod
    def create_download_url(
        dlkey: str,
        filename: str,
        derived: bool = False,
        expires: t.Optional[datetime.timedelta | int] = datetime.timedelta(hours=1),
        download_filename: t.Optional[str] = None
    ) -> str:
        """
            Utility function that creates a signed download-url for the given folder/filename combination

            :param folder: The GCS-Folder (= the download-key) for that file
            :param filename: The name of the file. Either the original filename or the name of a derived file.
            :param derived: True, if it points to a derived file, False if it points to the original uploaded file
            :param expires:
                None if the file is supposed to be public (which causes it to be cached on the google ede caches),
                otherwise a datetime.timedelta of how long that link should be valid
            :param download_filename: If set, browser is enforced to download this blob with the given alternate
                filename
            :return: The signed download-url relative to the current domain (eg /download/...)
        """
        if isinstance(expires, int):
            expires = datetime.timedelta(minutes=expires)

        # Undo escaping on ()= performed on fileNames
        filename = filename.replace("&#040;", "(").replace("&#041;", ")").replace("&#061;", "=")
        filepath = f"""{dlkey}/{"derived" if derived else "source"}/{filename}"""

        if download_filename:
            if not File.is_valid_filename(download_filename):
                raise errors.UnprocessableEntity(f"Invalid download_filename {download_filename!r} provided")

            download_filename = urlquote(download_filename)

        expires = (datetime.datetime.now() + expires).strftime("%Y%m%d%H%M") if expires else 0

        data = base64.urlsafe_b64encode(f"""{filepath}\0{expires}\0{download_filename or ""}""".encode("UTF-8"))
        sig = File.hmac_sign(data)

        return f"""{File.DOWNLOAD_URL_PREFIX}{data.decode("ASCII")}?sig={sig}"""

    @staticmethod
    def parse_download_url(url) -> t.Optional[FilePath]:
        """
        Parses a file download URL in the format `/file/download/xxxx?sig=yyyy` into its FilePath.

        If the URL cannot be parsed, the function returns None.

        :param url: The file download URL to be parsed.
        :return: A FilePath on success, None otherwise.
        """
        if not url.startswith(File.DOWNLOAD_URL_PREFIX) or "?" not in url:
            return None

        data, sig = url.removeprefix(File.DOWNLOAD_URL_PREFIX).split("?", 1)  # Strip "/file/download/" and split on "?"
        sig = sig.removeprefix("sig=")

        if not File.hmac_verify(data, sig):
            # Invalid signature
            return None

        # Split the blobKey into the individual fields it should contain
        data = base64.urlsafe_b64decode(data).decode("UTF-8")

        match data.count("\0"):
            case 2:
                dlpath, valid_until, _ = data.split("\0")
            case 1:
                # It's the old format, without an downloadFileName
                dlpath, valid_until = data.split("\0")
            case _:
                # Invalid path
                return None

        if valid_until != "0" and datetime.strptime(valid_until, "%Y%m%d%H%M") < datetime.now():
            # Signature expired
            return None

        if dlpath.count("/") != 2:
            # Invalid path
            return None

        dlkey, derived, filename = dlpath.split("/")
        return FilePath(dlkey, derived != "source", filename)

    @staticmethod
    def create_src_set(
        file: t.Union["SkeletonInstance", dict, str],
        expires: t.Optional[datetime.timedelta | int] = datetime.timedelta(hours=1),
        width: t.Optional[int] = None,
        height: t.Optional[int] = None,
        language: t.Optional[str] = None,
    ) -> str:
        """
            Generates a string suitable for use as the srcset tag in html. This functionality provides the browser
            with a list of images in different sizes and allows it to choose the smallest file that will fill it's
            viewport without upscaling.

            :param file: The file skeleton (or if multiple=True a single value from it) to generate the srcset.
            :param expires:
                None if the file is supposed to be public (which causes it to be cached on the google edecaches),
                otherwise it's lifetime in seconds
            :param width:
                A list of widths that should be included in the srcset.
                If a given width is not available, it will be skipped.
            :param height: A list of heights that should be included in the srcset. If a given height is not available,
                it will be skipped.
            :param language: Language overwrite if file has multiple languages, and we want to explicitly specify one
            :return: The srctag generated or an empty string if a invalid file object was supplied
        """
        if not width and not height:
            logging.error("Neither width or height supplied")
            return ""

        if isinstance(file, str):
            file = db.Query("file").filter("dlkey =", file).order(("creationdate", db.SortOrder.Ascending)).getEntry()

        if not file:
            return ""

        if isinstance(file, LanguageWrapper):
            language = language or current.language.get()
            if not language or not (file := file.get(language)):
                return ""

        if "dlkey" not in file and "dest" in file:
            file = file["dest"]

        from viur.core.skeleton import SkeletonInstance  # avoid circular imports

        if not (
            isinstance(file, (SkeletonInstance, dict))
            and "dlkey" in file
            and "derived" in file
        ):
            logging.error("Invalid file supplied")
            return ""

        if not isinstance(file["derived"], dict):
            logging.error("No derives available")
            return ""

        src_set = []
        for filename, derivate in file["derived"]["files"].items():
            customData = derivate.get("customData", {})

            if width and customData.get("width") in width:
                src_set.append(
                    f"""{File.create_download_url(file["dlkey"], filename, True, expires)} {customData["width"]}w"""
                )

            if height and customData.get("height") in height:
                src_set.append(
                    f"""{File.create_download_url(file["dlkey"], filename, True, expires)} {customData["height"]}h"""
                )

        return ", ".join(src_set)

    def write(
        self,
        filename: str,
        content: t.Any,
        mimetype: str = "text/plain",
        width: int = None,
        height: int = None,
        public: bool = False,
    ) -> db.Key:
        """
        Write a file from any buffer into the file module.

        :param filename: Filename to be written.
        :param content:  The file content to be written, as bytes-like object.
        :param mimetype: The file's mimetype.
        :param width: Optional width information for the file.
        :param height: Optional height information for the file.
        :param public: True if the file should be publicly accessible.
        :return: Returns the key of the file object written. This can be associated e.g. with a FileBone.
        """
        if not File.is_valid_filename(filename):
            raise ValueError(f"{filename=} is invalid")

        dl_key = utils.string.random()

        if public:
            dl_key += PUBLIC_DLKEY_SUFFIX  # mark file as public

        bucket = File.get_bucket(dl_key)

        blob = bucket.blob(f"{dl_key}/source/{filename}")
        blob.upload_from_file(io.BytesIO(content), content_type=mimetype)

        skel = self.addSkel("leaf")
        skel["name"] = filename
        skel["size"] = blob.size
        skel["mimetype"] = mimetype
        skel["dlkey"] = dl_key
        skel["weak"] = True
        skel["public"] = public
        skel["width"] = width
        skel["height"] = height
        skel["crc32c_checksum"] = base64.b64decode(blob.crc32c).hex()
        skel["md5_checksum"] = base64.b64decode(blob.md5_hash).hex()

        skel.write()
        return skel["key"]

    def read(
        self,
        key: db.Key | int | str | None = None,
        path: str | None = None,
    ) -> tuple[io.BytesIO, str]:
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
            if not skel.read(db.keyHelper(key, skel.kindName)):
                if not path:
                    raise ValueError("This skeleton is not in the database!")
            else:
                path = f"""{skel["dlkey"]}/source/{skel["name"]}"""

            bucket = File.get_bucket(skel["dlkey"])
        else:
            bucket = File.get_bucket(path.split("/", 1)[0])  # path's first part is dlkey plus eventual postfix

        blob = bucket.blob(path)
        return io.BytesIO(blob.download_as_bytes()), blob.content_type

    @CallDeferred
    def deleteRecursive(self, parentKey):
        files = db.Query(self.leafSkelCls().kindName).filter("parentdir =", parentKey).iter()
        for fileEntry in files:
            self.mark_for_deletion(fileEntry["dlkey"])
            skel = self.leafSkelCls()

            if skel.read(str(fileEntry.key())):
                skel.delete()
        dirs = db.Query(self.nodeSkelCls().kindName).filter("parentdir", parentKey).iter()
        for d in dirs:
            self.deleteRecursive(d.key)
            skel = self.nodeSkelCls()
            if skel.read(d.key):
                skel.delete()

    @exposed
    @skey
    def getUploadURL(
        self,
        fileName: str,
        mimeType: str,
        size: t.Optional[int] = None,
        node: t.Optional[str | db.Key] = None,
        authData: t.Optional[str] = None,
        authSig: t.Optional[str] = None,
        public: bool = False,
    ):
        filename = fileName.strip()  # VIUR4 FIXME: just for compatiblity of the parameter names

        if not File.is_valid_filename(filename):
            raise errors.UnprocessableEntity(f"Invalid filename {filename!r} provided")

        # Validate the mimetype from the client seems legit
        mimetype = mimeType.strip().lower()
        if not (
            mimetype
            and mimetype.count("/") == 1
            and all(ch in string.ascii_letters + string.digits + "/-.+" for ch in mimetype)
        ):
            raise errors.UnprocessableEntity(f"Invalid mime-type {mimetype!r} provided")

        # Validate authentication data
        if authData and authSig:
            # First, validate the signature, otherwise we don't need to proceed further
            if not self.hmac_verify(authData, authSig):
                raise errors.Unauthorized()

            authData = json.loads(base64.b64decode(authData.encode("ASCII")).decode("UTF-8"))

            if datetime.datetime.strptime(authData["validUntil"], "%Y%m%d%H%M") < datetime.datetime.now():
                raise errors.Gone("The upload URL has expired")

            if authData["validMimeTypes"]:
                for validMimeType in authData["validMimeTypes"]:
                    if (
                        validMimeType == mimetype
                        or (validMimeType.endswith("*") and mimetype.startswith(validMimeType[:-1]))
                    ):
                        break
                else:
                    raise errors.UnprocessableEntity(f"Invalid mime-type {mimetype} provided")

            node = authData["node"]
            maxSize = authData["maxSize"]

        else:
            rootNode = None
            if node and not (rootNode := self.getRootNode(node)):
                raise errors.NotFound(f"No valid root node found for {node=}")

            if not self.canAdd("leaf", rootNode):
                raise errors.Forbidden()

            maxSize = None  # The user has some file/add permissions, don't restrict fileSize

        if maxSize:
            if size > maxSize:
                raise errors.UnprocessableEntity(f"Size {size} exceeds maximum size {maxSize}")
        else:
            size = None

        # Create upload-URL and download key
        dlkey = utils.string.random()  # let's roll a random key

        if public:
            dlkey += PUBLIC_DLKEY_SUFFIX  # mark file as public

        blob = File.get_bucket(dlkey).blob(f"{dlkey}/source/{filename}")
        upload_url = blob.create_resumable_upload_session(content_type=mimeType, size=size, timeout=60)

        # Create a corresponding file-lock object early, otherwise we would have to ensure that the file-lock object
        # the user creates matches the file he had uploaded
        file_skel = self.addSkel("leaf")

        file_skel["name"] = filename + self.PENDING_POSTFIX
        file_skel["size"] = 0
        file_skel["mimetype"] = "application/octetstream"
        file_skel["dlkey"] = dlkey
        file_skel["parentdir"] = None
        file_skel["pendingparententry"] = db.keyHelper(node, self.addSkel("node").kindName) if node else None
        file_skel["pending"] = True
        file_skel["weak"] = True
        file_skel["public"] = public
        file_skel["width"] = 0
        file_skel["height"] = 0

        file_skel.write()
        key = str(file_skel["key"])

        # Mark that entry dirty as we might never receive an add
        self.mark_for_deletion(dlkey)

        # In this case, we'd have to store the key in the users session so he can call add() later on
        if authData and authSig:
            session = current.session.get()

            if "pendingFileUploadKeys" not in session:
                session["pendingFileUploadKeys"] = []

            session["pendingFileUploadKeys"].append(key)

            # Clamp to the latest 50 pending uploads
            session["pendingFileUploadKeys"] = session["pendingFileUploadKeys"][-50:]
            session.markChanged()

        return self.render.view({
            "uploadKey": key,
            "uploadUrl": upload_url,
        })

    @exposed
    def download(self, blobKey: str, fileName: str = "", download: bool = False, sig: str = "", *args, **kwargs):
        """
        Download a file.
        :param blobKey: The unique blob key of the file.
        :param fileName: Optional filename to provide in the header.
        :param download: Set header to attachment retrival, set explictly to "1" if download is wanted.
        """
        if filename := fileName.strip():
            if not File.is_valid_filename(filename):
                raise errors.UnprocessableEntity(f"The provided filename {filename!r} is invalid!")

        download_filename = ""

        try:
            dlPath, validUntil, download_filename = base64.urlsafe_b64decode(
                blobKey).decode("UTF-8").split("\0")
        except Exception as e:  # It's the old format, without an downloadFileName
            dlPath, validUntil = base64.urlsafe_b64decode(blobKey).decode(
                "UTF-8").split("\0")

        bucket = File.get_bucket(dlPath.split("/", 1)[0])

        if not sig:
            # Check if the current user has the right to download *any* blob present in this application.
            # blobKey is then the path inside cloudstore - not a base64 encoded tuple
            if not (usr := current.user.get()):
                raise errors.Unauthorized()
            if "root" not in usr["access"] and "file-view" not in usr["access"]:
                raise errors.Forbidden()
            validUntil = "-1"  # Prevent this from being cached down below
            blob = bucket.get_blob(blobKey)

        else:
            # We got an request including a signature (probably a guest or a user without file-view access)
            # First, validate the signature, otherwise we don't need to proceed any further
            if not self.hmac_verify(blobKey, sig):
                raise errors.Forbidden()

            if validUntil != "0" and datetime.datetime.strptime(validUntil, "%Y%m%d%H%M") < datetime.datetime.now():
                blob = None
            else:
                blob = bucket.get_blob(dlPath)

        if not blob:
            raise errors.Gone("The requested blob has expired.")

        if not filename:
            filename = download_filename or urlquote(blob.name.rsplit("/", 1)[-1])

        content_disposition = "; ".join(
            item for item in (
                "attachment" if download else None,
                f"filename={filename}" if filename else None,
            ) if item
        )

        if isinstance(_CREDENTIALS, ServiceAccountCredentials):
            expiresAt = datetime.datetime.now() + datetime.timedelta(seconds=60)
            signedUrl = blob.generate_signed_url(expiresAt, response_disposition=content_disposition, version="v4")
            raise errors.Redirect(signedUrl)

        elif conf.instance.is_dev_server:  # No Service-Account to sign with - Serve everything directly
            response = current.request.get().response
            response.headers["Content-Type"] = blob.content_type
            if content_disposition:
                response.headers["Content-Disposition"] = content_disposition
            return blob.download_as_bytes()

        if validUntil == "0" or blobKey.endswith(PUBLIC_DLKEY_SUFFIX):  # Its an indefinitely valid URL
            if blob.size < 5 * 1024 * 1024:  # Less than 5 MB - Serve directly and push it into the ede caches
                response = current.request.get().response
                response.headers["Content-Type"] = blob.content_type
                response.headers["Cache-Control"] = "public, max-age=604800"  # 7 Days
                if content_disposition:
                    response.headers["Content-Disposition"] = content_disposition
                return blob.download_as_bytes()

        # Default fallback - create a signed URL and redirect
        authRequest = google.auth.transport.requests.Request()
        expiresAt = datetime.datetime.now() + datetime.timedelta(seconds=60)
        signing_credentials = google.auth.compute_engine.IDTokenCredentials(authRequest, "")
        signedUrl = blob.generate_signed_url(
            expiresAt,
            credentials=signing_credentials,
            response_disposition=content_disposition,
            version="v4")

        raise errors.Redirect(signedUrl)

    SERVE_VALID_OPTIONS = {
        "c",
        "p",
        "fv",
        "fh",
        "r90",
        "r180",
        "r270",
        "nu",
    }
    """
    Valid modification option shorts for the serve-function.
    This is passed-through to the Google UserContent API, and hast to be supported there.
    """

    SERVE_VALID_FORMATS = {
        "jpg": "rj",
        "jpeg": "rj",
        "png": "rp",
        "webp": "rw",
    }
    """
    Valid file-formats to the serve-function.
    This is passed-through to the Google UserContent API, and hast to be supported there.
    """

    @exposed
    def serve(
        self,
        host: str,
        key: str,
        size: t.Optional[int] = None,
        filename: t.Optional[str] = None,
        options: str = "",
        download: bool = False,
    ):
        """
        Requests an image using the serving url to bypass direct Google requests.

        :param host: the google host prefix i.e. lh3
        :param key: the serving url key
        :param size: the target image size
        :param filename: a random string with an extention, valid extentions are (defined in File.SERVE_VALID_FORMATS).
        :param options: - seperated options (defined in File.SERVE_VALID_OPTIONS).
            c - crop
            p - face crop
            fv - vertrical flip
            fh - horizontal flip
            rXXX - rotate 90, 180, 270
            nu - no upscale
        :param download: Serves the content as download (Content-Disposition) or not.

        :return: Returns the requested content on success, raises a proper HTTP exception otherwise.
        """

        if any(c not in conf.search_valid_chars for c in host):
            raise errors.BadRequest("key contains invalid characters")

        # extract format from filename
        file_fmt = "webp"

        if filename:
            fmt = filename.rsplit(".", 1)[-1].lower()
            if fmt in self.SERVE_VALID_FORMATS:
                file_fmt = fmt
            else:
                raise errors.UnprocessableEntity(f"Unsupported filetype {fmt}")

        url = f"https://{host}.googleusercontent.com/{key}"

        if options and not all(param in self.SERVE_VALID_OPTIONS for param in options.split("-")):
            raise errors.BadRequest("Invalid options provided")

        options += f"-{self.SERVE_VALID_FORMATS[file_fmt]}"

        if size:
            options = f"s{size}-" + options

        url += "=" + options

        response = current.request.get().response
        response.headers["Content-Type"] = f"image/{file_fmt}"
        response.headers["Cache-Control"] = "public, max-age=604800"  # 7 Days
        if download:
            response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        else:
            response.headers["Content-Disposition"] = f"filename={filename}"

        answ = requests.get(url, timeout=20)
        if not answ.ok:
            logging.error(f"{answ.status_code} {answ.text}")
            raise errors.BadRequest("Unable to fetch a file with these parameters")

        return answ.content

    @exposed
    @force_ssl
    @force_post
    @skey(allow_empty=True)
    def add(self, skelType: SkelType, node: db.Key | int | str | None = None, *args, **kwargs):
        # We can't add files directly (they need to be uploaded
        if skelType == "leaf":  # We need to handle leafs separately here
            targetKey = kwargs.get("key")
            skel = self.addSkel("leaf")

            if not skel.read(targetKey):
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

            # Now read the blob from the dlkey folder
            bucket = File.get_bucket(skel["dlkey"])

            blobs = list(bucket.list_blobs(prefix=f"""{skel["dlkey"]}/"""))
            if len(blobs) != 1:
                logging.error("Invalid number of blobs in folder")
                logging.error(targetKey)
                raise errors.PreconditionFailed()

            # only one item is allowed here!
            blob = blobs[0]

            # update the corresponding file skeleton
            skel["name"] = skel["name"].removesuffix(self.PENDING_POSTFIX)
            skel["mimetype"] = utils.string.escape(blob.content_type)
            skel["size"] = blob.size
            skel["parentrepo"] = rootNode["key"] if rootNode else None
            skel["weak"] = rootNode is None
            skel["crc32c_checksum"] = base64.b64decode(blob.crc32c).hex()
            skel["md5_checksum"] = base64.b64decode(blob.md5_hash).hex()
            self.inject_serving_url(skel)

            skel.write()

            # Add updated download-URL as the auto-generated isn't valid yet
            skel["downloadUrl"] = self.create_download_url(skel["dlkey"], skel["name"])

            return self.render.addSuccess(skel)

        return super().add(skelType, node, *args, **kwargs)

    @exposed
    def get_download_url(
        self,
        key: t.Optional[db.Key] = None,
        dlkey: t.Optional[str] = None,
        filename: t.Optional[str] = None,
        derived: bool = False,

    ):
        """
        Request a download url for a given file
        :param key: The key of the file
        :param dlkey: The download key of the file
        :param filename: The filename to be given. If no filename is provided
            downloadUrls for all derived files are returned in case of `derived=True`.
        :param derived: True, if a derived file download URL is being requested.
        """
        skel = self.viewSkel("leaf")
        if dlkey is not None:
            skel = skel.all().filter("dlkey", dlkey).getSkel()
        elif key is None and dlkey is None:
            raise errors.BadRequest("No key or dlkey provided")

        if not (skel and skel.read(key)):
            raise errors.NotFound()

        if not self.canView("leaf", skel):
            raise errors.Unauthorized()

        dlkey = skel["dlkey"]

        if derived and filename is None:
            res = {}
            for filename in skel["derived"]["files"]:
                res[filename] = self.create_download_url(dlkey, filename, derived)
        else:
            if derived:
                # Check if Filename exist in the Derives. We sign nothing that not exist.
                if filename not in skel["derived"]["files"]:
                    raise errors.NotFound("File not in derives")
            else:
                if filename is None:
                    filename = skel["name"]
                elif filename != skel["name"]:
                    raise errors.NotFound("Filename not match")

            res = self.create_download_url(dlkey, filename, derived)

        return self.render.view(res)

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

        bucket = File.get_bucket(skel['dlkey'])

        if not (old_blob := bucket.get_blob(old_path)):
            raise errors.Gone()

        bucket.copy_blob(old_blob, bucket, new_path, if_generation_match=0)
        bucket.delete_blob(old_path)

        self.inject_serving_url(skel)

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

    def inject_serving_url(self, skel: SkeletonInstance) -> None:
        """Inject the serving url for public image files into a FileSkel"""
        if (
                skel["public"]
                and skel["mimetype"]
                and skel["mimetype"].startswith("image/")
                and not skel["serving_url"]
        ):
            bucket = File.get_bucket(skel["dlkey"])
            filename = f"/gs/{bucket.name}/{skel['dlkey']}/source/{skel['name']}"

            # Trying this on local development server will raise a
            # `google.appengine.runtime.apiproxy_errors.RPCFailedError`
            if conf.instance.is_dev_server:
                logging.warning(f"Can't inject serving_url for {filename!r} on local development server")
                return

            try:
                skel["serving_url"] = images.get_serving_url(None, secure_url=True, filename=filename)

            except Exception as e:
                logging.warning(f"Failed to create serving_url for {filename!r} with exception {e!r}")
                logging.exception(e)


@PeriodicTask(interval=datetime.timedelta(hours=4))
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


@PeriodicTask(interval=datetime.timedelta(hours=4))
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
        if "dlkey" not in file:
            db.Delete(file.key)
        elif db.Query("viur-blob-locks").filter("active_blob_references =", file["dlkey"]).getEntry():
            logging.info(f"""is referenced, {file["dlkey"]}""")
            db.Delete(file.key)
        else:
            if file["itercount"] > maxIterCount:
                logging.info(f"""Finally deleting, {file["dlkey"]}""")
                bucket = File.get_bucket(file["dlkey"])
                blobs = bucket.list_blobs(prefix=f"""{file["dlkey"]}/""")
                for blob in blobs:
                    blob.delete()
                db.Delete(file.key)
                # There should be exactly 1 or 0 of these
                for f in skeletonByKind("file")().all().filter("dlkey =", file["dlkey"]).fetch(99):
                    f.delete()

                    if f["serving_url"]:
                        bucket = File.get_bucket(f["dlkey"])
                        blob_key = blobstore.create_gs_key(
                            f"/gs/{bucket.name}/{f['dlkey']}/source/{f['name']}"
                        )
                        images.delete_serving_url(blob_key)  # delete serving url
            else:
                logging.debug(f"""Increasing count, {file["dlkey"]}""")
                file["itercount"] += 1
                db.Put(file)
    newCursor = query.getCursor()
    if newCursor:
        doCleanupDeletedFiles(newCursor)


@PeriodicTask(interval=datetime.timedelta(hours=4))
def start_delete_pending_files():
    """
    Start deletion of pending FileSkels that are older than 7 days.
    """
    DeleteEntitiesIter.startIterOnQuery(
        FileLeafSkel().all()
        .filter("pending =", True)
        .filter("creationdate <", utils.utcNow() - datetime.timedelta(days=7))
    )


# DEPRECATED ATTRIBUTES HANDLING

def __getattr__(attr: str) -> object:
    if entry := {
            # stuff prior viur-core < 3.7
            "GOOGLE_STORAGE_BUCKET": ("File.get_bucket()", _private_bucket),
    }.get(attr):
        msg = f"{attr} was replaced by {entry[0]}"
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        logging.warning(msg, stacklevel=2)
        return entry[1]

    return super(__import__(__name__).__class__).__getattribute__(attr)
