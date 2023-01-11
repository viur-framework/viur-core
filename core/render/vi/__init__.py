# noinspection PyUnresolvedReferences
from viur.core.render.vi.user import UserRender as user  # this import must exist!
from viur.core.render.json.default import DefaultRender, CustomJsonEncoder
from viur.core import conf, exposed, securitykey, utils, errors
from viur.core.utils import currentRequest, currentLanguage
from viur.core.skeleton import SkeletonInstance
from viur.core.prototypes import Module
import datetime, json


class default(DefaultRender):
    kind = "json.vi"


__all__ = [default]


@exposed
def genSkey(*args, **kwargs):
    return json.dumps(securitykey.create())

@exposed
def timestamp(*args, **kwargs):
    d = datetime.datetime.now()
    return json.dumps(d.strftime("%Y-%m-%dT%H-%M-%S"))


@exposed
def getStructure(module):
    """
    Returns all available skeleton structures for a given module.
    """
    moduleObj = getattr(conf["viur.mainApp"].vi, module, None)
    if not isinstance(moduleObj, Module):
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
                        res[storeType] = default().renderSkelStructure(skel)
    else:
        # every other prototype
        for stype in ("viewSkel", "editSkel", "addSkel"):  # Unknown skel type
            if stype in dir(moduleObj):
                try:
                    skel = getattr(moduleObj, stype)()
                except (TypeError, ValueError):
                    continue
                if isinstance(skel, SkeletonInstance):
                    res[stype] = default().renderSkelStructure(skel)

    currentRequest.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(res or None, cls=CustomJsonEncoder)


@exposed
def setLanguage(lang, skey):
    if not securitykey.validate(skey):
        return
    if lang in conf["viur.availableLanguages"]:
        currentLanguage.set(lang)

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
        "configuration": {k.removeprefix("admin."): v for k, v in conf.items() if k.lower().startswith("admin.")}
    }

    currentRequest.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(res)


@exposed
def getVersion(*args, **kwargs):
    """
    Returns viur-core version number
    """
    if conf["viur.instance.is_dev_server"]:
        json.dumps(conf["viur.version"])

    # Hide patchlevel
    return json.dumps((conf["viur.version"][0], conf["viur.version"][1], 0))


def canAccess(*args, **kwargs) -> bool:
    user = utils.getCurrentUser()
    if user and ("root" in user["access"] or "admin" in user["access"]):
        return True
    pathList = currentRequest.get().pathlist
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

    if conf["viur.instance.is_dev_server"] or currentRequest.get().isSSLConnection:
        raise errors.Redirect("/vi/s/main.html")

    else:
        appVersion = currentRequest.get().request.host
        raise errors.Redirect("https://%s/vi/s/main.html" % appVersion)


@exposed
def get_settings():
    fields = {key: values for key, values in conf.items()
              if key.startswith("admin.")}

    fields["admin.user.google.clientID"] = conf.get("viur.user.google.clientID", "")

    currentRequest.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(fields)


def _postProcessAppObj(obj):
    obj["skey"] = genSkey
    obj["timestamp"] = timestamp
    obj["config"] = dumpConfig
    obj["settings"] = get_settings
    obj["getStructure"] = getStructure
    obj["canAccess"] = canAccess
    obj["setLanguage"] = setLanguage
    obj["getVersion"] = getVersion
    obj["index"] = index
    return obj
