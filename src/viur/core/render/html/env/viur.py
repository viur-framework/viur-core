from collections import OrderedDict

import logging
import os
import typing as t
import urllib
import urllib.parse
from datetime import timedelta
from hashlib import sha512
from qrcode import make as qrcode_make
from qrcode.image import svg as qrcode_svg

import string
from viur.core import Method, current, db, errors, prototypes, securitykey, utils
from viur.core.config import conf
from viur.core.i18n import translate as translate_class
from viur.core.render.html.utils import jinjaGlobalFilter, jinjaGlobalFunction
from viur.core.request import TEMPLATE_STYLE_KEY
from viur.core.skeleton import RelSkel, SkeletonInstance
from viur.core.modules import file
from ..default import Render


@jinjaGlobalFunction
def translate(
    render: Render,
    key: str,
    default_text: str = None,
    hint: str = None,
    force_lang: str | None = None,
    **kwargs
) -> str:
    """Jinja function for translations

    See also :class:`core.i18n.TranslationExtension`.
    """
    return translate_class(key, default_text, hint, force_lang)(**kwargs)


@jinjaGlobalFunction
def execRequest(render: Render, path: str, *args, **kwargs) -> t.Any:
    """
    Jinja2 global: Perform an internal Request.

    This function allows to embed the result of another request inside the current template.
    All optional parameters are passed to the requested resource.

    :param path: Local part of the url, e.g. user/list. Must not start with an /.
        Must not include an protocol or hostname.

    :returns: Whatever the requested resource returns. This is *not* limited to strings!
    """
    request = current.request.get()
    cachetime = kwargs.pop("cachetime", 0)
    if conf.debug.disable_cache or request.disableCache:  # Caching disabled by config
        cachetime = 0
    cacheEnvKey = None
    if conf.cache_environment_key:
        try:
            cacheEnvKey = conf.cache_environment_key()
        except RuntimeError:
            cachetime = 0
    if cachetime:
        # Calculate the cache key that entry would be stored under
        tmpList = [f"{k}:{v}" for k, v in kwargs.items()]
        tmpList.sort()
        tmpList.extend(list(args))
        tmpList.append(path)
        if cacheEnvKey is not None:
            tmpList.append(cacheEnvKey)
        try:
            appVersion = request.request.environ["CURRENT_VERSION_ID"].split('.')[0]
        except:
            appVersion = ""
            logging.error("Could not determine the current application id! Caching might produce unexpected results!")
        tmpList.append(appVersion)
        mysha512 = sha512()
        mysha512.update(str(tmpList).encode("UTF8"))
        # TODO: Add hook for optional memcache or remove these remnants
        cacheKey = f"jinja2_cache_{mysha512.hexdigest()}"
        res = None  # memcache.get(cacheKey)
        if res:
            return res
    # Pop this key after building the cache string with it
    template_style = kwargs.pop(TEMPLATE_STYLE_KEY, None)
    tmp_params = request.kwargs.copy()
    request.kwargs = {"__args": args, "__outer": tmp_params}
    request.kwargs.update(kwargs)
    lastRequestState = request.internalRequest
    request.internalRequest = True
    last_template_style = request.template_style
    request.template_style = template_style
    caller = conf.main_app
    pathlist = path.split("/")
    for currpath in pathlist:
        if currpath in dir(caller):
            caller = getattr(caller, currpath)
        elif "index" in dir(caller) and hasattr(getattr(caller, "index"), '__call__'):
            caller = getattr(caller, "index")
        else:
            request.kwargs = tmp_params  # Reset RequestParams
            request.internalRequest = lastRequestState
            request.template_style = last_template_style
            return f"{path=} not found (failed at {currpath!r})"

    if not (isinstance(caller, Method) and caller.exposed is not None):
        request.kwargs = tmp_params  # Reset RequestParams
        request.internalRequest = lastRequestState
        request.template_style = last_template_style
        return f"{caller!r} not callable or not exposed"
    try:
        resstr = caller(*args, **kwargs)
    except Exception as e:
        logging.error(f"Caught exception in execRequest while calling {path}")
        logging.exception(e)
        raise
    request.kwargs = tmp_params
    request.internalRequest = lastRequestState
    request.template_style = last_template_style
    if cachetime:
        pass
    # memcache.set(cacheKey, resstr, cachetime)
    return resstr


@jinjaGlobalFunction
def getCurrentUser(render: Render) -> t.Optional[SkeletonInstance]:
    """
    Jinja2 global: Returns the current user from the session, or None if not logged in.

    :return: A dict containing user data. Returns None if no user data is available.
    """
    currentUser = current.user.get()
    if currentUser:
        currentUser = currentUser.clone()  # need to clone, as renderPreparation is changed
        currentUser.renderPreparation = render.renderBoneValue
    return currentUser


@jinjaGlobalFunction
def getSkel(render: Render, module: str, key: str = None, skel: str = "viewSkel") -> dict | bool | None:
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
    if module not in dir(conf.main_app):
        logging.error(f"getSkel called with unknown {module=}!")
        return False

    obj = getattr(conf.main_app, module)

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
                logging.info(f"getSkel: Entry {key} not found")
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
                logging.error(f"getSkel: Access to {key} denied from canView")
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
    url = current.request.get().request.url
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
    return conf.instance.version_hash


@jinjaGlobalFunction
def getAppVersion(render: Render) -> str:
    """
    Jinja2 global: Return the application version for the current version as set on deployment.
    :return: The current version
    """
    return conf.instance.app_version


@jinjaGlobalFunction
def redirect(render: Render, url: str) -> t.NoReturn:
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
        using conf.i18n.language_alias_map.
    """
    lang = current.language.get()
    if resolveAlias and lang in conf.i18n.language_alias_map:
        lang = conf.i18n.language_alias_map[lang]
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
            _noEmptyFilter: bool = False, *args, **kwargs) -> bool | None | list[SkeletonInstance]:
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
    if module not in dir(conf.main_app):
        logging.error(f"Jinja2-Render can't fetch a list from an unknown module {module}!")
        return False
    caller = getattr(conf.main_app, module)
    if "viewSkel" not in dir(caller):
        logging.error(f"Jinja2-Render cannot fetch a list from {module} due to missing viewSkel function")
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
                 subSkel: t.Optional[str] = None) -> dict | bool:
    """
    Jinja2 global: Returns the skeleton structure instead of data for a module.

    :param render: The html-renderer instance.
    :param module: Module from which the skeleton is retrieved.
    :param skel: Name of the skeleton.
    :param subSkel: If set, return just that subskel instead of the whole skeleton
    """
    if module not in dir(conf.main_app):
        return False

    obj = getattr(conf.main_app, module)

    if skel in dir(obj):
        skel = getattr(obj, skel)()

        if isinstance(skel, SkeletonInstance) or isinstance(skel, RelSkel):
            if subSkel is not None:
                try:
                    skel = skel.subSkel(subSkel)

                except Exception as e:
                    logging.exception(e)
                    return False

            return skel.structure()

    return False


@jinjaGlobalFunction
def requestParams(render: Render) -> dict[str, str]:
    """
    Jinja2 global: Allows for accessing the request-parameters from the template.

    These returned values are escaped, as users tend to use these in an unsafe manner.

    :returns: dict of parameter and values.
    """
    res = {}
    for k, v in current.request.get().kwargs.items():
        res[utils.string.escape(k)] = utils.string.escape(v)
    return res


@jinjaGlobalFunction
def updateURL(render: Render, **kwargs) -> str:
    """
    Jinja2 global: Constructs a new URL based on the current requests url.

    Given parameters are replaced if they exists in the current requests url, otherwise there appended.

    :returns: Returns a well-formed URL.
    """
    tmpparams = {}
    tmpparams.update(current.request.get().kwargs)

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
def fileSize(render: Render, value: int | float, binary: bool = False) -> str:
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

    return f'{(base * bytes / unit):.1f} {prefix}'


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
def shortKey(render: Render, val: str) -> t.Optional[str]:
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
        raise ValueError(f"Bone {boneName} is not part of that skeleton")

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
                   skel: dict,
                   ignore: list[str] = None,
                   hide: list[str] = None,
                   prefix=None,
                   bones: list[str] = None,
                   ) -> str:
    """Render an edit-form based on a skeleton.

    Render an HTML-form with lables and inputs from the skeleton structure
    using templates for each bone-types.

    :param render: The html-renderer instance.
    :param skel: The skelton which provides the structure.
    :param ignore: Don't render fields for these bones (name of the bone).
    :param hide: Render these fields as hidden fields (name of the bone).
    :param prefix: Prefix added to the bone names.
    :param bones: If set only the bone with a name in the list would be rendered.

    :return: A string containing the HTML-form.
    """
    if not isinstance(skel, dict) or not all([x in skel.keys() for x in ["errors", "structure", "value"]]):
        raise ValueError("This does not look like an editable Skeleton!")

    res = ""

    sectionTpl = render.getEnv().get_template(render.getTemplateFileName("editform_category"))
    rowTpl = render.getEnv().get_template(render.getTemplateFileName("editform_row"))
    sections = OrderedDict()

    if ignore and bones and (both := set(ignore).intersection(bones)):
        raise ValueError(f"You have specified the same bones {', '.join(both)} in *ignore* AND *bones*!")
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
            if bones and boneName not in bones:
                continue
            # print("--- skel[\"errors\"] ---")
            # print(skel["errors"])

            pathToBone = ((prefix + ".") if prefix else "") + boneName
            boneErrors = [entry for entry in skel["errors"] if ".".join(entry.fieldPath).startswith(pathToBone)]

            if hide and boneName in hide:
                boneParams["visible"] = False

            if not boneParams["readonly"]:
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
            categoryClassName="".join(ch for ch in str(category) if ch in string.ascii_letters),
            categoryContent=categoryContent,
            allReadOnly=allReadOnly,
            allHidden=allHidden
        )

    return res


@jinjaGlobalFunction
def embedSvg(render: Render, name: str, classes: list[str] | None = None, **kwargs: dict[str, str]) -> str:
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
        "src": os.path.join(conf.static_embed_svg_path, f"{name}.svg"),
        "class": " ".join(classes),
        **kwargs
    }
    return f"""<img {" ".join(f'{k}="{v}"' for k, v in attributes.items())}>"""


@jinjaGlobalFunction
def downloadUrlFor(
    render: Render,
    fileObj: dict,
    expires: t.Optional[int] = conf.render_html_download_url_expiration,
    derived: t.Optional[str] = None,
    downloadFileName: t.Optional[str] = None
) -> str:
    """
    Constructs a signed download-url for the given file-bone. Mostly a wrapper around
        :meth:`file.File.create_download_url`.

        :param render: The jinja renderer instance
        :param fileObj: The file-bone (eg. skel["file"])
        :param expires:
            None if the file is supposed to be public
            (which causes it to be cached on the google ede caches), otherwise it's lifetime in seconds.
        :param derived:
            Optional the filename of a derived file,
            otherwise the download-link will point to the originally uploaded file.
        :param downloadFileName: The filename to use when saving the response payload locally.
        :return: THe signed download-url relative to the current domain (eg /download/...)
    """
    if "dlkey" not in fileObj and "dest" in fileObj:
        fileObj = fileObj["dest"]

    if expires:
        expires = timedelta(minutes=expires)

    if not isinstance(fileObj, (SkeletonInstance, dict)) or "dlkey" not in fileObj or "name" not in fileObj:
        logging.error("Invalid fileObj supplied")
        return ""

    if derived and ("derived" not in fileObj or not isinstance(fileObj["derived"], dict)):
        logging.error("No derivation for this fileObj")
        return ""

    if derived:
        return file.File.create_download_url(
            fileObj["dlkey"],
            filename=derived,
            derived=True,
            expires=expires,
            download_filename=downloadFileName,
        )

    return file.File.create_download_url(
        fileObj["dlkey"],
        filename=fileObj["name"],
        expires=expires,
        download_filename=downloadFileName
    )


@jinjaGlobalFunction
def srcSetFor(
    render: Render,
    fileObj: dict,
    expires: t.Optional[int] = conf.render_html_download_url_expiration,
    width: t.Optional[int] = None,
    height: t.Optional[int] = None
) -> str:
    """
    Generates a string suitable for use as the srcset tag in html. This functionality provides the browser with a list
    of images in different sizes and allows it to choose the smallest file that will fill it's viewport without
    upscaling.

        :param render:
            The render instance that's calling this function.
        :param fileObj:
            The file-bone (or if multiple=True a single value from it) to generate the srcset for.
        :param expires: None if the file is supposed to be public
            (which causes it to be cached on the google ede caches), otherwise it's lifetime in seconds.
        :param width: A list of widths that should be included in the srcset.
            If a given width is not available, it will be skipped.
        :param height: A list of heights that should be included in the srcset.
            If a given height is not available, it will be skipped.

    :return: The srctag generated or an empty string if a invalid file object was supplied
    """
    return file.File.create_src_set(fileObj, expires, width, height)


@jinjaGlobalFunction
def seoUrlForEntry(render: Render, *args, **kwargs):
    return utils.seoUrlToEntry(*args, **kwargs)


@jinjaGlobalFunction
def seoUrlToFunction(render: Render, *args, **kwargs):
    return utils.seoUrlToFunction(*args, **kwargs)


@jinjaGlobalFunction
def qrcode(render: Render, data: str) -> str:
    """
    Generates a SVG string for a html template

    :param data: Any string data that should render to a QR Code.

    :return: The SVG string representation.
    """
    return qrcode_make(data, image_factory=qrcode_svg.SvgPathImage, box_size=30).to_string().decode("utf-8")
