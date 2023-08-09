# noinspection PyUnresolvedReferences
from viur.core.render.vi.user import UserRender as user  # this import must exist!
from viur.core.render.json import skey
from viur.core.render.json.default import DefaultRender, CustomJsonEncoder
from viur.core.render.vi.user import UserRender as user
from viur.core import Module, conf, current, exposed, securitykey, errors
from viur.core.skeleton import SkeletonInstance
import datetime
import json


class default(DefaultRender):
    kind = "json.vi"


__all__ = [default]


@exposed
def timestamp(*args, **kwargs):
    d = datetime.datetime.now()
    current.request.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(d.strftime("%Y-%m-%dT%H-%M-%S"))


@exposed
def getStructure(module):
    """
    Returns all available skeleton structures for a given module.
    """
    moduleObj = getattr(conf["viur.mainApp"].vi, module, None)
    if not isinstance(moduleObj, Module) or not moduleObj.describe():
        return json.dumps(None)

    res = {}

    # check for tree prototype
    if "nodeSkelCls" in dir(moduleObj):
        # Try Node/Leaf
        for stype in ("viewSkel", "editSkel", "addSkel"):
            for treeType in ("node", "leaf"):
                if stype in dir(moduleObj):
                    try:
                        skel = getattr(moduleObj, stype)(treeType)
                    except (TypeError, ValueError):
                        continue

                    if isinstance(skel, SkeletonInstance):
                        storeType = stype.replace("Skel", "") + ("LeafSkel" if treeType == "leaf" else "NodeSkel")
                        res[storeType] = DefaultRender.render_structure(skel.structure())
    else:
        # every other prototype
        for stype in ("viewSkel", "editSkel", "addSkel"):  # Unknown skel type
            if stype in dir(moduleObj):
                try:
                    skel = getattr(moduleObj, stype)()
                except (TypeError, ValueError):
                    continue
                if isinstance(skel, SkeletonInstance):
                    res[stype] = DefaultRender.render_structure(skel.structure())

    current.request.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(res or None, cls=CustomJsonEncoder)


@exposed
def setLanguage(lang, skey):
    if not securitykey.validate(skey):
        raise errors.PreconditionFailed()

    if lang in conf["viur.availableLanguages"]:
        current.language.set(lang)


@exposed
def dumpConfig():
    res = {}

    for key in dir(conf["viur.mainApp"].vi):
        module = getattr(conf["viur.mainApp"].vi, key, None)
        if not isinstance(module, Module):
            continue

        if admin_info := module.describe():
            res[key] = admin_info

    res = {
        "modules": res,
        "configuration": {
            k.removeprefix("admin."): v for k, v in conf.items() if k.lower().startswith("admin.")
        }
    }
    current.request.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(res, cls=CustomJsonEncoder)


@exposed
def getVersion(*args, **kwargs):
    """
    Returns viur-core version number
    """
    current.request.get().response.headers["Content-Type"] = "application/json"

    version = conf["viur.version"]

    # always fill up to 4 parts
    while len(version) < 4:
        version += (None,)

    if conf["viur.instance.is_dev_server"] \
            or ((cuser := current.user.get()) and ("root" in cuser["access"] or "admin" in cuser["access"])):
        return json.dumps(version[:4])

    # Hide patch level + appendix to non-authorized users
    return json.dumps((version[0], version[1], None, None))


def canAccess(*args, **kwargs) -> bool:
    if (user := current.user.get()) and ("root" in user["access"] or "admin" in user["access"]):
        return True
    pathList = current.request.get().path_list
    if len(pathList) >= 2 and pathList[1] in ["skey", "getVersion", "settings"]:
        # Give the user the chance to login :)
        return True
    if (len(pathList) >= 3
        and pathList[1] == "user"
        and (pathList[2].startswith("auth_")
             or pathList[2].startswith("f2_")
             or pathList[2] == "getAuthMethods"
             or pathList[2] == "logout")):
        # Give the user the chance to login :)
        return True
    if (len(pathList) >= 4
        and pathList[1] == "user"
        and pathList[2] == "view"
        and pathList[3] == "self"):
        # Give the user the chance to view himself.
        return True
    return False


@exposed
def index(*args, **kwargs):
    if not conf["viur.instance.project_base_path"].joinpath("vi", "main.html").exists():
        raise errors.NotFound()
    if conf["viur.instance.is_dev_server"] or current.request.get().isSSLConnection:
        raise errors.Redirect("/vi/s/main.html")
    else:
        appVersion = current.request.get().request.host
        raise errors.Redirect("https://%s/vi/s/main.html" % appVersion)


@exposed
def get_settings():
    fields = {key: values for key, values in conf.items()
              if key.startswith("admin.")}

    fields["admin.user.google.clientID"] = conf.get("viur.user.google.clientID", "")

    current.request.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(fields)


def _postProcessAppObj(obj):
    obj["skey"] = skey
    obj["timestamp"] = timestamp
    obj["config"] = dumpConfig
    obj["settings"] = get_settings
    obj["getStructure"] = getStructure
    obj["canAccess"] = canAccess
    obj["setLanguage"] = setLanguage
    obj["getVersion"] = getVersion
    obj["index"] = index
    return obj
