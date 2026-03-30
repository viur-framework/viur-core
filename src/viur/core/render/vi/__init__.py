import datetime
import fnmatch
import json
import logging
from viur.core import Module, conf, current, errors
from viur.core.decorators import *
from viur.core.render.json import skey as json_render_skey
from viur.core.render.json.default import CustomJsonEncoder, DefaultRender
from viur.core.skeleton import SkeletonInstance
from deprecated.sphinx import deprecated


class default(DefaultRender):
    kind = "json.vi"


__all__ = [default]


@exposed
def timestamp(*args, **kwargs):
    d = datetime.datetime.now()
    current.request.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(d.strftime("%Y-%m-%dT%H-%M-%S"))


@exposed
@deprecated(version="3.9.0", reason="Use '/vi/module/structure' as new endpoint")
def getStructure(module):
    """
    Returns all available skeleton structures for a given module.

    To access the structure of a nested module, separate the path with dots (.).
    """
    logging.warning(
        f"DEPRECATED!!! Use '/vi/{module}/structure' or '/json/{module}/structure' for this, "
        "or update your admin version!"
    )

    path = module.split(".")
    moduleObj = conf.main_app.vi
    while path:
        moduleObj = getattr(moduleObj, path.pop(0), None)
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
@skey
def setLanguage(lang):
    if lang in conf.i18n.available_languages:
        current.language.set(lang)


@exposed
def getVersion(*args, **kwargs):
    """
    Returns viur-core version number
    """
    current.request.get().response.headers["Content-Type"] = "application/json"

    version = conf.version

    # always fill up to 4 parts
    while len(version) < 4:
        version += (None,)

    if conf.instance.is_dev_server or _can_access(current.user.get()):
        return json.dumps(version[:4])

    # Hide patch level + appendix to non-authorized users
    return json.dumps((version[0], version[1], None, None))


def _can_access(user_skel: SkeletonInstance) -> bool:
    """
    Internal check for vi-render if a given user is allowed to use this render.
    The function is used in several places for better integration.
    """
    return bool(user_skel and "admin" in user_skel["access"])


def canAccess(*args, **kwargs) -> bool:
    """
    General access restrictions for the vi-render.
    """
    if _can_access(current.user.get()):
        return True

    return any(fnmatch.fnmatch(current.request.get().path, pat) for pat in conf.security.admin_allowed_paths)


@exposed
def index(*args, **kwargs):
    if args or kwargs:
        raise errors.NotFound()
    if (
        not conf.instance.project_base_path.joinpath("vi", "main.html").exists()
        and not conf.instance.project_base_path.joinpath("admin", "main.html").exists()
    ):
        raise errors.NotFound()
    if conf.instance.is_dev_server or current.request.get().isSSLConnection:
        raise errors.Redirect("/vi/s/main.html")
    else:
        appVersion = current.request.get().request.host
        raise errors.Redirect(f"https://{appVersion}/vi/s/main.html")


@exposed
def get_config():
    """
    Get public admin-tool specific settings, requires no user to be logged in.
    This is used by new vi-admin.
    """
    current.request.get().response.headers["Content-Type"] = "application/json"

    result = {}
    config = {k.replace("_", "."): v for k, v in conf.admin.items(True)}

    if conf.user.google_client_id:
        config["admin.user.google.clientID"] = conf.user.google_client_id

    config["admin.language"] = current.language.get() or conf.i18n.default_language
    config["admin.languages"] = conf.i18n.available_languages

    if _can_access(current.user.get()):
        modules = {}
        visited_objects = set()

        def collect_modules(parent, depth: int = 0) -> None:
            """Recursively collects all routable modules for the vi renderer"""
            if depth > 10:
                logging.warning(f"Reached maximum recursion limit of {depth} at {parent=}")
                return

            for key in dir(parent):
                module = getattr(parent, key, None)
                if not isinstance(module, Module):
                    continue

                if module in visited_objects:
                    # Some modules reference other modules as parents, this will
                    # lead to infinite recursion. We can avoid reaching the
                    # maximum recursion limit by remembering already seen modules.
                    if conf.debug.trace:
                        logging.debug(f"Already visited and added {module=}")
                    continue

                visited_objects.add(module)

                if admin_info := module.describe():
                    # map path --> config
                    modules[module.modulePath.removeprefix("/vi/").replace("/", ".")] = admin_info

                # Collect children
                collect_modules(module, depth=depth + 1)

        collect_modules(conf.main_app.vi)

        result["modules"] = modules

    result["configuration"] = config
    return json.dumps(result, cls=CustomJsonEncoder)


def _postProcessAppObj(obj):
    obj["skey"] = json_render_skey
    obj["timestamp"] = timestamp
    obj["config"] = get_config
    obj["getStructure"] = getStructure
    obj["canAccess"] = canAccess
    obj["setLanguage"] = setLanguage
    obj["getVersion"] = getVersion
    obj["index"] = index
    return obj
