from collections import OrderedDict

import logging
import os
import string
import urllib
import urllib.parse
from datetime import timedelta
from hashlib import sha512
from typing import Any, Dict, List, NoReturn, Optional, Union

import viur.core.render.html.default
from viur.core import db, errors, prototypes, securitykey, utils
from viur.core.config import conf
from viur.core.i18n import translate as translationClass
from viur.core.render.html.utils import jinjaGlobalFilter, jinjaGlobalFunction
from viur.core.skeleton import RelSkel, SkeletonInstance
from viur.core.utils import currentLanguage, currentRequest
from ..default import Render


@jinjaGlobalFunction
def translate(render: Render, key: str, **kwargs) -> str:
    res = str(translationClass(key))
    for k, v in kwargs.items():
        res = res.replace("{{%s}}" % k, str(v))
    return res


@jinjaGlobalFunction
def execRequest(render: Render, path: str, *args, **kwargs) -> Any:
    """
    Jinja2 global: Perform an internal Request.

    This function allows to embed the result of another request inside the current template.
    All optional parameters are passed to the requested resource.

    :param path: Local part of the url, e.g. user/list. Must not start with an /.
        Must not include an protocol or hostname.

    :returns: Whatever the requested resource returns. This is *not* limited to strings!
    """
    cachetime = kwargs.pop("cachetime", 0)
    if conf["viur.disableCache"] or currentRequest.get().disableCache:  # Caching disabled by config
        cachetime = 0
    cacheEnvKey = None
    if conf["viur.cacheEnvironmentKey"]:
        try:
            cacheEnvKey = conf["viur.cacheEnvironmentKey"]()
        except RuntimeError:
            cachetime = 0
    if cachetime:
        # Calculate the cache key that entry would be stored under
        tmpList = ["%s:%s" % (str(k), str(v)) for k, v in kwargs.items()]
        tmpList.sort()
        tmpList.extend(list(args))
        tmpList.append(path)
        if cacheEnvKey is not None:
            tmpList.append(cacheEnvKey)
        try:
            appVersion = currentRequest.get().request.environ["CURRENT_VERSION_ID"].split('.')[0]
        except:
            appVersion = ""
            logging.error("Could not determine the current application id! Caching might produce unexpected results!")
        tmpList.append(appVersion)
        mysha512 = sha512()
        mysha512.update(str(tmpList).encode("UTF8"))
        # TODO: Add hook for optional memcache or remove these remnants
        cacheKey = "jinja2_cache_%s" % mysha512.hexdigest()
        res = None  # memcache.get(cacheKey)
        if res:
            return res
    currReq = currentRequest.get()
    tmp_params = currReq.kwargs.copy()
    currReq.kwargs = {"__args": args, "__outer": tmp_params}
    currReq.kwargs.update(kwargs)
    lastRequestState = currReq.internalRequest
    currReq.internalRequest = True
    caller = conf["viur.mainApp"]
    pathlist = path.split("/")
    for currpath in pathlist:
        if currpath in dir(caller):
            caller = getattr(caller, currpath)
        elif "index" in dir(caller) and hasattr(getattr(caller, "index"), '__call__'):
            caller = getattr(caller, "index")
        else:
            currReq.kwargs = tmp_params  # Reset RequestParams
            currReq.internalRequest = lastRequestState
            return u"Path not found %s (failed Part was %s)" % (path, currpath)
    if (not hasattr(caller, '__call__')
        or ((not "exposed" in dir(caller)
             or not caller.exposed))
        and (not "internalExposed" in dir(caller)
             or not caller.internalExposed)):
        currReq.kwargs = tmp_params  # Reset RequestParams
        currReq.internalRequest = lastRequestState
        return u"%s not callable or not exposed" % str(caller)
    try:
        resstr = caller(*args, **kwargs)
    except Exception as e:
        logging.error("Caught execption in execRequest while calling %s" % path)
        logging.exception(e)
        raise
    currReq.kwargs = tmp_params
    currReq.internalRequest = lastRequestState
    if cachetime:
        pass
    # memcache.set(cacheKey, resstr, cachetime)
    return resstr


@jinjaGlobalFunction
def getCurrentUser(render: Render) -> Optional[SkeletonInstance]:
    """
    Jinja2 global: Returns the current user from the session, or None if not logged in.

    :return: A dict containing user data. Returns None if no user data is available.
    """
    currentUser = utils.getCurrentUser()
    if currentUser:
        currentUser.renderPreparation = render.renderBoneValue
    return currentUser


@jinjaGlobalFunction
def getSkel(render: Render, module: str, key: str = None, skel: str = "viewSkel") -> Union[dict, bool, None]:
    """
    Jinja2 global: Fetch an entry from a given module, and return the data as a dict,
    prepared for direct use in the output.

    It is possible to specify a different data-model as the one used for rendering
    (e.g. an editSkel).

    :param module: Name of the module, from which the data should be fetched.
    :param key: Requested entity-key in an urlsafe-format. If the module is a Singleton
    application, the parameter can be omitted.
    :param skel: Specifies and optionally different data-model

    :returns: dict on success, False on error.
    """
    if module not in dir(conf["viur.mainApp"]):
        logging.error("getSkel called with unknown module %s!" % module)
        return False

    obj = getattr(conf["viur.mainApp"], module)

    if skel in dir(obj):
        skel = getattr(obj, skel)()

        if isinstance(obj, prototypes.singleton.Singleton) and not key:
            # We fetching the entry from a singleton - No key needed
            key = db.Key(skel.kindName, obj.getKey())
        elif not key:
            logging.info("getSkel called without a valid key")
            return False

        if not isinstance(skel, SkeletonInstance):
            return False

        if "canView" in dir(obj):
            if not skel.fromDB(key):
                logging.info("getSkel: Entry %s not found" % (key,))
                return None
            if isinstance(obj, prototypes.singleton.Singleton):
                isAllowed = obj.canView()
            elif isinstance(obj, prototypes.tree.Tree):
                k = db.Key(key)
                if k.kind.endswith("_rootNode"):
                    isAllowed = obj.canView("node", skel)
                else:
                    isAllowed = obj.canView("leaf", skel)
            else:  # List and Hierarchies
                isAllowed = obj.canView(skel)
            if not isAllowed:
                logging.error("getSkel: Access to %s denied from canView" % (key,))
                return None
        elif "listFilter" in dir(obj):
            qry = skel.all().mergeExternalFilter({"key": str(key)})
            qry = obj.listFilter(qry)
            if not qry:
                logging.info("listFilter permits getting entry, returning None")
                return None

            skel = qry.getSkel()
            if not skel:
                return None

        else:  # No Access-Test for this module
            if not skel.fromDB(key):
                return None
        skel.renderPreparation = render.renderBoneValue
        return skel

    return False


@jinjaGlobalFunction
def getHostUrl(render: Render, forceSSL=False, *args, **kwargs):
    """
    Jinja2 global: Retrieve hostname with protocol.

    :returns: Returns the hostname, including the currently used protocol, e.g: http://www.example.com
    :rtype: str
    """
    url = currentRequest.get().request.url
    url = url[:url.find("/", url.find("://") + 5)]
    if forceSSL and url.startswith("http://"):
        url = "https://" + url[7:]
    return url


@jinjaGlobalFunction
def getVersionHash(render: Render) -> str:
    """
    Jinja2 global: Return the application hash for the current version. This can be used for cache-busting in
            resource links (eg. /static/css/style.css?v={{ getVersionHash() }}. This hash is stable for each version
            deployed (identical across all instances), but will change whenever a new version is deployed.
    :return: The current version hash
    """
    return conf["viur.instance.version_hash"]


@jinjaGlobalFunction
def getAppVersion(render: Render) -> str:
    """
    Jinja2 global: Return the application version for the current version as set on deployment.
    :return: The current version
    """
    return conf["viur.instance.app_version"]


@jinjaGlobalFunction
def redirect(render: Render, url: str) -> NoReturn:
    """
    Jinja2 global: Redirect to another URL.

    :param url: URL to redirect to.

    :raises: :exc:`viur.core.errors.Redirect`
    """
    raise errors.Redirect(url)


@jinjaGlobalFunction
def getLanguage(render: Render, resolveAlias: bool = False) -> str:
    """
    Jinja2 global: Returns the language used for this request.

    :param resolveAlias: If True, the function tries to resolve the current language
        using conf["viur.languageAliasMap"].
    """
    lang = currentLanguage.get()
    if resolveAlias and lang in conf["viur.languageAliasMap"]:
        lang = conf["viur.languageAliasMap"][lang]
    return lang


@jinjaGlobalFunction
def moduleName(render: Render) -> str:
    """
    Jinja2 global: Retrieve name of current module where this renderer is used within.

    :return: Returns the name of the current module, or empty string if there is no module set.
    """
    if render.parent and "moduleName" in dir(render.parent):
        return render.parent.moduleName
    return ""


@jinjaGlobalFunction
def modulePath(render: Render) -> str:
    """
    Jinja2 global: Retrieve path of current module the renderer is used within.

    :return: Returns the path of the current module, or empty string if there is no module set.
    """
    if render.parent and "modulePath" in dir(render.parent):
        return render.parent.modulePath
    return ""


@jinjaGlobalFunction
def getList(render: Render, module: str, skel: str = "viewSkel",
            _noEmptyFilter: bool = False, *args, **kwargs) -> Union[bool, None, List[SkeletonInstance]]:
    """
    Jinja2 global: Fetches a list of entries which match the given filter criteria.

    :param render: The html-renderer instance.
    :param module: Name of the module from which list should be fetched.
    :param skel: Name of the skeleton that is used to fetching the list.
    :param _noEmptyFilter: If True, this function will not return any results if at least one
        parameter is an empty list. This is useful to prevent filtering (e.g. by key) not being
        performed because the list is empty.
    :returns: Returns a dict that contains the "skellist" and "cursor" information,
        or None on error case.
    """
    if not module in dir(conf["viur.mainApp"]):
        logging.error("Jinja2-Render can't fetch a list from an unknown module %s!" % module)
        return False
    caller = getattr(conf["viur.mainApp"], module)
    if not "viewSkel" in dir(caller):
        logging.error("Jinja2-Render cannot fetch a list from %s due to missing viewSkel function" % module)
        return False
    if _noEmptyFilter:  # Test if any value of kwargs is an empty list
        if any([isinstance(x, list) and not len(x) for x in kwargs.values()]):
            return []
    query = getattr(caller, "viewSkel")(skel).all()
    query.mergeExternalFilter(kwargs)
    if "listFilter" in dir(caller):
        query = caller.listFilter(query)
    if query is None:
        return None
    mylist = query.fetch()
    if mylist:
        for skel in mylist:
            skel.renderPreparation = render.renderBoneValue
    return mylist


@jinjaGlobalFunction
def getSecurityKey(render: Render, **kwargs) -> str:
    """
    Jinja2 global: Creates a new ViUR security key.
    """
    return securitykey.create(**kwargs)


@jinjaGlobalFunction
def getStructure(render: Render,
                 module: str,
                 skel: str = "viewSkel",
                 subSkel: Optional[str] = None) -> Union[Dict, bool]:
    """
    Jinja2 global: Returns the skeleton structure instead of data for a module.

    :param render: The html-renderer instance.
    :param module: Module from which the skeleton is retrieved.
    :param skel: Name of the skeleton.
    :param subSkel: If set, return just that subskel instead of the whole skeleton
    """
    if not module in dir(conf["viur.mainApp"]):
        return False

    obj = getattr(conf["viur.mainApp"], module)

    if skel in dir(obj):
        skel = getattr(obj, skel)()

        if isinstance(skel, SkeletonInstance) or isinstance(skel, RelSkel):
            if subSkel is not None:
                try:
                    skel = skel.subSkel(subSkel)
                except Exception as e:
                    logging.exception(e)
                    return False

            return render.renderSkelStructure(skel)

    return False


@jinjaGlobalFunction
def requestParams(render: Render) -> Dict[str, str]:
    """
    Jinja2 global: Allows for accessing the request-parameters from the template.

    These returned values are escaped, as users tend to use these in an unsafe manner.

    :returns: dict of parameter and values.
    """
    res = {}
    for k, v in currentRequest.get().kwargs.items():
        res[utils.escapeString(k)] = utils.escapeString(v)
    return res


@jinjaGlobalFunction
def updateURL(render: Render, **kwargs) -> str:
    """
    Jinja2 global: Constructs a new URL based on the current requests url.

    Given parameters are replaced if they exists in the current requests url, otherwise there appended.

    :returns: Returns a well-formed URL.
    """
    tmpparams = {}
    tmpparams.update(currentRequest.get().kwargs)

    for key in list(tmpparams.keys()):
        if not key or key[0] == "_":
            del tmpparams[key]

    for key, value in list(kwargs.items()):
        if value is None:
            if key in tmpparams:
                del tmpparams[key]
        else:
            tmpparams[key] = value

    return "?" + urllib.parse.urlencode(tmpparams).replace("&", "&amp;")


@jinjaGlobalFilter
def fileSize(render: Render, value: Union[int, float], binary: bool = False) -> str:
    """
    Jinja2 filter: Format the value in an 'human-readable' file size (i.e. 13 kB, 4.1 MB, 102 Bytes, etc).
    Per default, decimal prefixes are used (Mega, Giga, etc.). When the second parameter is set to True,
    the binary prefixes are used (Mebi, Gibi).

    :param render: The html-renderer instance.
    :param value: Value to be calculated.
    :param binary: Decimal prefixes behavior

    :returns: The formatted file size string in human readable format.
    """
    bytes = float(value)
    base = binary and 1024 or 1000

    prefixes = [
        (binary and 'KiB' or 'kB'),
        (binary and 'MiB' or 'MB'),
        (binary and 'GiB' or 'GB'),
        (binary and 'TiB' or 'TB'),
        (binary and 'PiB' or 'PB'),
        (binary and 'EiB' or 'EB'),
        (binary and 'ZiB' or 'ZB'),
        (binary and 'YiB' or 'YB')
    ]

    if bytes == 1:
        return '1 Byte'
    elif bytes < base:
        return '%d Bytes' % bytes

    unit = 0
    prefix = ""

    for i, prefix in enumerate(prefixes):
        unit = base ** (i + 2)
        if bytes < unit:
            break

    return '%.1f %s' % ((base * bytes / unit), prefix)


@jinjaGlobalFilter
def urlencode(render: Render, val: str) -> str:
    """
    Jinja2 filter: Make a string URL-safe.

    :param render: The html-renderer instance.
    :param val: String to be quoted.
    :returns: Quoted string.
    """
    # quote_plus fails if val is None
    if not val:
        return ""

    if isinstance(val, str):
        val = val.encode("UTF-8")

    return urllib.parse.quote_plus(val)


# TODO
'''
This has been disabled until we are sure
    a) what use-cases it has
    b) how it's best implemented
    c) doesn't introduce any XSS vulnerability
  - TS 13.03.2016
@jinjaGlobalFilter
def className(render: Render, s: str) -> str:
    """
    Jinja2 filter: Converts a URL or name into a CSS-class name, by replacing slashes by underscores.
    Example call could be```{{self|string|toClassName}}```.

    :param s: The string to be converted, probably ``self|string`` in the Jinja2 template.

    :return: CSS class name.
    """
    l = re.findall('\'([^\']*)\'', str(s))
    if l:
        l = set(re.split(r'/|_', l[0].replace(".html", "")))
        return " ".join(l)

    return ""
'''


@jinjaGlobalFilter
def shortKey(render: Render, val: str) -> Optional[str]:
    """
    Jinja2 filter: Make a shortkey from an entity-key.

    :param render: The html-renderer instance.
    :param val: Entity-key as string.

    :returns: Shortkey on success, None on error.
    """
    try:
        k = db.Key.from_legacy_urlsafe(str(val))
        return k.id_or_name
    except:
        return None


@jinjaGlobalFunction
def renderEditBone(render: Render, skel, boneName, boneErrors=None, prefix=None):
    if not isinstance(skel, dict) or not all([x in skel for x in ["errors", "structure", "value"]]):
        raise ValueError("This does not look like an editable Skeleton!")

    boneParams = skel["structure"].get(boneName)

    if not boneParams:
        raise ValueError("Bone %s is not part of that skeleton" % boneName)

    if not boneParams["visible"]:
        fileName = "editform_bone_hidden"
    else:
        fileName = "editform_bone_" + boneParams["type"]

    while fileName:
        try:
            fn = render.getTemplateFileName(fileName)
            break

        except errors.NotFound:
            if "." in fileName:
                fileName, unused = fileName.rsplit(".", 1)
            else:
                fn = render.getTemplateFileName("editform_bone_bone")
                break

    tpl = render.getEnv().get_template(fn)

    return tpl.render(
        boneName=((prefix + ".") if prefix else "") + boneName,
        boneParams=boneParams,
        boneValue=skel["value"][boneName] if boneName in skel["value"] else None,
        boneErrors=boneErrors
    )


@jinjaGlobalFunction
def renderEditForm(render: Render,
                   skel: Dict,
                   ignore:List[str]=None,
                   hide:List[str]=None,
                   prefix=None) -> str:
    """Render an edit-form based on a skeleton.

    Render an HTML-form with lables and inputs from the skeleton structure
    using templates for each bone-types.

    :param render: The html-renderer instance.
    :param skel: The skelton which provides the structure.
    :param ignore: Don't render fields for these bones (name of the bone).
    :param hide: Render these fields as hidden fields (name of the bone).
    :param prefix: Prefix added to the bone names.

    :return: A string containing the HTML-form.
    """
    if not isinstance(skel, dict) or not all([x in skel.keys() for x in ["errors", "structure", "value"]]):
        raise ValueError("This does not look like an editable Skeleton!")

    res = ""

    sectionTpl = render.getEnv().get_template(render.getTemplateFileName("editform_category"))
    rowTpl = render.getEnv().get_template(render.getTemplateFileName("editform_row"))
    sections = OrderedDict()
    for boneName, boneParams in skel["structure"].items():
        category = str("server.render.html.default_category")
        if "params" in boneParams and isinstance(boneParams["params"], dict):
            category = boneParams["params"].get("category", category)
        if not category in sections:
            sections[category] = []

        sections[category].append((boneName, boneParams))

    for category, boneList in sections.items():
        allReadOnly = True
        allHidden = True
        categoryContent = ""

        for boneName, boneParams in boneList:
            if ignore and boneName in ignore:
                continue

            # print("--- skel[\"errors\"] ---")
            # print(skel["errors"])

            pathToBone = ((prefix + ".") if prefix else "") + boneName
            boneErrors = [entry for entry in skel["errors"] if ".".join(entry.fieldPath).startswith(pathToBone)]

            if hide and boneName in hide:
                boneParams["visible"] = False

            if not boneParams["readOnly"]:
                allReadOnly = False

            if boneParams["visible"]:
                allHidden = False

            editWidget = renderEditBone(render, skel, boneName, boneErrors, prefix=prefix)
            categoryContent += rowTpl.render(
                boneName=pathToBone,
                boneParams=boneParams,
                boneErrors=boneErrors,
                editWidget=editWidget
            )

        res += sectionTpl.render(
            categoryName=category,
            categoryClassName="".join([x for x in category if x in string.ascii_letters]),
            categoryContent=categoryContent,
            allReadOnly=allReadOnly,
            allHidden=allHidden
        )

    return res


@jinjaGlobalFunction
def embedSvg(render: Render, name: str, classes: Union[List[str], None] = None, **kwargs: Dict[str, str]) -> str:
    """
    jinja2 function to get an <img/>-tag for a SVG.
    This method will not check the existence of a SVG!

    :param render: The jinja renderer instance
    :param name: Name of the icon (basename of file)
    :param classes: A list of css-classes for the <img/>-tag
    :param kwargs: Further html-attributes for this tag (e.g. "alt" or "title")
    :return: A <img/>-tag
    """
    if any([x in name for x in ["..", "~", "/"]]):
        return ""

    if classes is None:
        classes = ["js-svg", name.split("-", 1)[0]]
    else:
        assert isinstance(classes, list), "*classes* must be a list"
        classes.extend(["js-svg", name.split("-", 1)[0]])

    attributes = {
        "src": os.path.join(conf["viur.static.embedSvg.path"], f"{name}.svg"),
        "class": " ".join(classes),
        **kwargs
    }
    return "<img %s>" % " ".join(f"{k}=\"{v}\"" for k, v in attributes.items())


@jinjaGlobalFunction
def downloadUrlFor(render: Render,
                   fileObj: dict,
                   expires: Union[None, int] = conf["viur.render.html.downloadUrlExpiration"],
                   derived: Optional[str] = None,
                   downloadFileName: Optional[str] = None) -> Optional[str]:
    """
        Constructs a signed download-url for the given file-bone. Mostly a wrapper around
        :meth:`viur.core.utils.downloadUrlFor`.

        :param render: The jinja renderer instance
        :param fileObj: The file-bone (eg. skel["file"])
        :param expires: None if the file is supposed to be public (which causes it to be cached on the google ede
            caches), otherwise it's lifetime in seconds
        :param derived: Optional the filename of a derived file, otherwise the download-link will point to the
            originally uploaded file.
        :param downloadFileName: The filename to use when saving the response payload locally.
        :return: THe signed download-url relative to the current domain (eg /download/...)
    """
    if "dlkey" not in fileObj and "dest" in fileObj:
        fileObj = fileObj["dest"]
    if expires:
        expires = timedelta(minutes=expires)
    if not isinstance(fileObj, (SkeletonInstance, dict)) or "dlkey" not in fileObj or "name" not in fileObj:
        return None
    if derived and ("derived" not in fileObj or not isinstance(fileObj["derived"], dict)):
        return None
    if derived:
        return utils.downloadUrlFor(folder=fileObj["dlkey"], fileName=derived, derived=True, expires=expires,
                                    downloadFileName=downloadFileName)
    else:
        return utils.downloadUrlFor(folder=fileObj["dlkey"], fileName=fileObj["name"], derived=False, expires=expires,
                                    downloadFileName=downloadFileName)


@jinjaGlobalFunction
def srcSetFor(render: Render, fileObj: dict, expires: Optional[int],
              width: Optional[int] = None, height: Optional[int] = None) -> str:
    """
        Generates a string suitable for use as the srcset tag in html. This functionality provides the browser
        with a list of images in different sizes and allows it to choose the smallest file that will fill it's viewport
        without upscaling.
        :param render: The render instance that's calling this function
        :param fileObj: The file-bone (or if multiple=True a single value from it) to generate the srcset for
        :param expires: None if the file is supposed to be public (which causes it to be cached on the google ede
            caches), otherwise it's lifetime in seconds
        :param width: A list of widths that should be included in the srcset. If a given width is not available, it will
            be skipped.
        :param height: A list of heights that should be included in the srcset. If a given height is not available,
            it will    be skipped.
        :return: The srctag generated or an empty string if a invalid file object was supplied
    """
    return utils.srcSetFor(fileObj, expires, width, height)


@jinjaGlobalFunction
def seoUrlForEntry(render: Render, *args, **kwargs):
    return utils.seoUrlToEntry(*args, **kwargs)


@jinjaGlobalFunction
def seoUrlToFunction(render: Render, *args, **kwargs):
    return utils.seoUrlToFunction(*args, **kwargs)
