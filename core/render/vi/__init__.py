from viur.core.prototypes import List
from viur.core.render.json.default import DefaultRender, CustomJsonEncoder
from viur.core.render.vi.user import UserRender as user
from viur.core import conf, exposed
from viur.core import securitykey
from viur.core import utils
from viur.core import errors
import datetime, json
from viur.core.utils import currentRequest, currentLanguage
from viur.core.skeleton import SkeletonInstance


class default(DefaultRender):
    kind = "json.vi"


__all__ = [default]


def genSkey(*args, **kwargs):
    return json.dumps(securitykey.create())


genSkey.exposed = True


def timestamp(*args, **kwargs):
    d = datetime.datetime.now()
    return json.dumps(d.strftime("%Y-%m-%dT%H-%M-%S"))


timestamp.exposed = True


def getStructure(adminTree, module):
    """
    Returns all available skeleton structures for a given module.
    """
    if not module in dir(adminTree) \
        or not "adminInfo" in dir(getattr(adminTree, module)) \
        or not getattr(adminTree, module).adminInfo:
        # Module not known or no adminInfo for that module
        return json.dumps(None)

    res = {}
    try:
        moduleObj = getattr(adminTree, module)
    except:
        return json.dumps(None)

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


def setLanguage(lang, skey):
    if not securitykey.validate(skey):
        return
    if lang in conf["viur.availableLanguages"]:
        currentLanguage.set(lang)


setLanguage.exposed = True


def dumpConfig(adminTree):
    adminConfig = {}
    for key in dir(adminTree):
        app = getattr(adminTree, key)
        if "adminInfo" in dir(app) and app.adminInfo:
            if callable(app.adminInfo):
                info = app.adminInfo()
                if info is not None:
                    adminConfig[key] = info
            else:
                adminConfig[key] = app.adminInfo.copy()
                adminConfig[key]["name"] = str(adminConfig[key]["name"])
                adminConfig[key]["views"] = []
                if "views" in app.adminInfo:
                    for v in app.adminInfo["views"]:
                        tmp = v.copy()
                        tmp["name"] = str(tmp["name"])
                        adminConfig[key]["views"].append(tmp)
        if key in adminConfig:
            adminConfig[key]["indexes"] = getattr(app, "indexes", [])

    res = {
        "modules": adminConfig,
        "configuration": {}
    }

    for k, v in conf.items():
        if k.lower().startswith("admin."):
            res["configuration"][k[6:]] = v

    currentRequest.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(res)


def getVersion(*args, **kwargs):
    # We force the patch-level of our version to be always zero for security reasons
    return json.dumps((conf["viur.version"][0], conf["viur.version"][1], 0))


getVersion.exposed = True


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


def index(*args, **kwargs):
    from viur.core.render import isAdminAvailable, isViAvailable
    if not isViAvailable():
        if isAdminAvailable():
            # The Vi is not available, the admin however is, so redirect there
            raise errors.Redirect("/admin")
        raise errors.NotFound()
    if conf["viur.instance.is_dev_server"] or currentRequest.get().isSSLConnection:
        raise errors.Redirect("/vi/s/main.html")
    else:
        appVersion = currentRequest.get().request.host
        raise errors.Redirect("https://%s/vi/s/main.html" % appVersion)


index.exposed = True


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
    obj["config"] = lambda *args, **kwargs: dumpConfig(conf["viur.mainApp"].vi)
    obj["config"].exposed = True
    obj["settings"] = get_settings
    obj["getStructure"] = lambda *args, **kwargs: getStructure(conf["viur.mainApp"].vi, *args, **kwargs)
    obj["getStructure"].exposed = True
    obj["canAccess"] = canAccess
    obj["setLanguage"] = setLanguage
    obj["getVersion"] = getVersion
    obj["index"] = index
    return obj
