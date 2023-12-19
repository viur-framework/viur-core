import hashlib
import hmac
import warnings

import logging
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
import typing as t
from urllib.parse import quote
from viur.core import current, db
from viur.core.config import conf
from . import string, parse


def utcNow() -> datetime:
    return datetime.now(timezone.utc)



def getCurrentUser() -> t.Optional["SkeletonInstance"]:
    """
        Retrieve current user, if logged in.
        If a user is logged in, this function returns a dict containing user data.
        If no user is logged in, the function returns None.

        :returns: A SkeletonInstance containing information about the logged-in user, None if no user is logged in.
    """
    import warnings
    msg = f"Use of `utils.getCurrentUser()` is deprecated; Use `current.user.get()` instead!"
    warnings.warn(msg, DeprecationWarning, stacklevel=3)
    logging.warning(msg, stacklevel=3)
    return current.user.get()


def markFileForDeletion(dlkey: str) -> None:
    """
    Adds a marker to the data store that the file specified as *dlkey* can be deleted.

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

def hmacSign(data: t.Any) -> str:
    assert conf.file_hmac_key is not None, "No hmac-key set!"
    if not isinstance(data, bytes):
        data = str(data).encode("UTF-8")
    return hmac.new(conf.file_hmac_key, msg=data, digestmod=hashlib.sha3_384).hexdigest()


def hmacVerify(data: t.Any, signature: str) -> bool:
    return hmac.compare_digest(hmacSign(data), signature)


def sanitizeFileName(fileName: str) -> str:
    """
        Sanitize the filename so it can be safely downloaded or be embedded into html
    """
    fileName = fileName[:100]  # Limit to 100 Chars max
    fileName = "".join([x for x in fileName if x not in "\0'\"<>\n;$&?#:;/\\"])  # Remove invalid Chars
    fileName = fileName.strip(".")  # Ensure the filename does not start or end with a dot
    fileName = quote(fileName)  # Finally quote any non-ASCII characters
    return fileName


def downloadUrlFor(folder: str, fileName: str, derived: bool = False,
                   expires: timedelta | None = timedelta(hours=1),
                   downloadFileName: t.Optional[str] = None) -> str:
    """
        Utility function that creates a signed download-url for the given folder/filename combination

        :param folder: The GCS-Folder (= the download-key) for that file
        :param fileName: The name of that file. Either the original filename as uploaded or the name of a dervived file
        :param derived: True, if it points to a derived file, False if it points to the original uploaded file
        :param expires:
            None if the file is supposed to be public (which causes it to be cached on the google ede caches),
            otherwise a timedelta of how long that link should be valid
        :param downloadFileName: If set, we'll force to browser to download this blob with the given filename
        :return: THe signed download-url relative to the current domain (eg /download/...)
    """
    # Undo escaping on ()= performed on fileNames
    fileName = fileName.replace("&#040;", "(").replace("&#041;", ")").replace("&#061;", "=")
    if derived:
        filePath = "%s/derived/%s" % (folder, fileName)
    else:
        filePath = "%s/source/%s" % (folder, fileName)
    if downloadFileName:
        downloadFileName = sanitizeFileName(downloadFileName)
    else:
        downloadFileName = ""
    expires = ((datetime.now() + expires).strftime("%Y%m%d%H%M") if expires else 0)
    sigStr = "%s\0%s\0%s" % (filePath, expires, downloadFileName)
    sigStr = urlsafe_b64encode(sigStr.encode("UTF-8"))
    resstr = hmacSign(sigStr)
    return "/file/download/%s?sig=%s" % (sigStr.decode("ASCII"), resstr)


def srcSetFor(fileObj: dict, expires: t.Optional[int], width: t.Optional[int] = None,
              height: t.Optional[int] = None) -> str:
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
        logging.error("Neither width or height supplied to srcSetFor")
        return ""
    if "dlkey" not in fileObj and "dest" in fileObj:
        fileObj = fileObj["dest"]
    if expires:
        expires = timedelta(minutes=expires)
    from viur.core.skeleton import SkeletonInstance  # avoid circular imports
    if not isinstance(fileObj, (SkeletonInstance, dict)) or not "dlkey" in fileObj or "derived" not in fileObj:
        logging.error("Invalid fileObj supplied to srcSetFor")
        return ""
    if not isinstance(fileObj["derived"], dict):
        return ""
    resList = []
    for fileName, derivate in fileObj["derived"]["files"].items():
        customData = derivate.get("customData", {})
        if width and customData.get("width") in width:
            resList.append("%s %sw" % (downloadUrlFor(fileObj["dlkey"], fileName, True, expires), customData["width"]))
        if height and customData.get("height") in height:
            resList.append("%s %sh" % (downloadUrlFor(fileObj["dlkey"], fileName, True, expires), customData["height"]))
    return ", ".join(resList)


def seoUrlToEntry(module: str,
                  entry: t.Optional["SkeletonInstance"] = None,
                  skelType: t.Optional[str] = None,
                  language: t.Optional[str] = None) -> str:
    """
    Return the seo-url to a skeleton instance or the module.

    :param module: The module name.
    :param entry: A skeleton instance or None, to get the path to the module.
    :param skelType: # FIXME: Not used
    :param language: For which language.
        If None, the language of the current request is used.
    :return: The path (with a leading /).
    """
    from viur.core import conf
    pathComponents = [""]
    if language is None:
        language = current.language.get()
    if conf.i18n.language_method == "url":
        pathComponents.append(language)
    if module in conf.i18n.language_module_map and language in conf.i18n.language_module_map[module]:
        module = conf.i18n.language_module_map[module][language]
    pathComponents.append(module)
    if not entry:
        return "/".join(pathComponents)
    else:
        try:
            currentSeoKeys = entry["viurCurrentSeoKeys"]
        except:
            return "/".join(pathComponents)
        if language in (currentSeoKeys or {}):
            pathComponents.append(str(currentSeoKeys[language]))
        elif "key" in entry:
            key = entry["key"]
            if isinstance(key, str):
                try:
                    key = db.Key.from_legacy_urlsafe(key)
                except:
                    pass
            pathComponents.append(str(key.id_or_name) if isinstance(key, db.Key) else str(key))
        elif "name" in dir(entry):
            pathComponents.append(str(entry.name))
        return "/".join(pathComponents)


def seoUrlToFunction(module: str, function: str, render: t.Optional[str] = None) -> str:
    from viur.core import conf
    lang = current.language.get()
    if module in conf.i18n.language_module_map and lang in conf.i18n.language_module_map[module]:
        module = conf.i18n.language_module_map[module][lang]
    if conf.i18n.language_method == "url":
        pathComponents = ["", lang]
    else:
        pathComponents = [""]
    targetObject = conf.main_resolver
    if module in targetObject:
        pathComponents.append(module)
        targetObject = targetObject[module]
    if render and render in targetObject:
        pathComponents.append(render)
        targetObject = targetObject[render]
    if function in targetObject:
        func = targetObject[function]
        if func.seo_language_map and lang in func.seo_language_map:
            pathComponents.append(func.seo_language_map[lang])
        else:
            pathComponents.append(function)
    return "/".join(pathComponents)


def normalizeKey(key: t.Union[None, 'db.KeyClass']) -> t.Union[None, 'db.KeyClass']:
    """
        Normalizes a datastore key (replacing _application with the current one)

        :param key: Key to be normalized.

        :return: Normalized key in string representation.
    """
    if key is None:
        return None
    if key.parent:
        parent = normalizeKey(key.parent)
    else:
        parent = None
    return db.Key(key.kind, key.id_or_name, parent=parent)


# DEPRECATED ATTRIBUTES HANDLING
__UTILS_CONF_REPLACEMENT = {
    "projectID": "viur.instance.project_id",
    "isLocalDevelopmentServer": "viur.instance.is_dev_server",
    "projectBasePath": "viur.instance.project_base_path",
    "coreBasePath": "viur.instance.core_base_path"
}

__UTILS_NAME_REPLACEMENT = {
    "currentRequest": ("current.request", current.request),
    "currentRequestData": ("current.request_data", current.request_data),
    "currentSession": ("current.session", current.session),
    "currentLanguage": ("current.language", current.language),
    "generateRandomString": ("utils.string.random", string.random),
    "escapeString": ("utils.string.escape", string.escape),
    "is_prefix": ("utils.string.is_prefix", string.is_prefix),
    "parse_bool": ("utils.parse.bool", parse.bool),
}


def __getattr__(attr):
    if replace := __UTILS_CONF_REPLACEMENT.get(attr):
        msg = f"Use of `utils.{attr}` is deprecated; Use `conf.{replace}` instead!"
        warnings.warn(msg, DeprecationWarning, stacklevel=3)
        logging.warning(msg, stacklevel=3)
        return conf[replace]

    if replace := __UTILS_NAME_REPLACEMENT.get(attr):
        msg = f"Use of `utils.{attr}` is deprecated; Use `{replace[0]}` instead!"
        warnings.warn(msg, DeprecationWarning, stacklevel=3)
        logging.warning(msg, stacklevel=3)
        return replace[1]

    return super(__import__(__name__).__class__).__getattr__(attr)