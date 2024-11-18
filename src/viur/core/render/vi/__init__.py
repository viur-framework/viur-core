import datetime
import fnmatch
import json
import logging
from viur.core import Module, conf, current, errors
from viur.core.decorators import exposed, skey
from viur.core.render.json import skey as json_render_skey, initialize
from viur.core.render.json.default import CustomJsonEncoder, DefaultRender
from viur.core.render.json.user import UserRender
from viur.core.skeleton import SkeletonInstance
from deprecated.sphinx import deprecated


class default(DefaultRender):
    kind = "json.vi"


class user(UserRender):
    kind = "json.vi.user"


__all__ = [default, user]


@exposed
def timestamp(*args, **kwargs):
    d = datetime.datetime.now()
    return json.dumps(d.strftime("%Y-%m-%dT%H-%M-%S"))


@exposed
@deprecated(
    version="3.7.0",
    reason="Don't use this anymore; Use /vi/your-module/structure + the wanted skeleton for that.",
    action="always"
)
def getStructure(module):
    """
    Returns all available skeleton structures for a given module.

    To access the structure of a nested module, separate the path with dots (.).
    """
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

    return json.dumps(res or None, cls=CustomJsonEncoder)


@exposed
@skey
def setLanguage(lang):
    if lang in conf.i18n.available_languages:
        current.language.set(lang)


@exposed
def dumpConfig():
    res = {}
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
                res[module.modulePath.removeprefix("/vi/").replace("/", ".")] = admin_info
            # Collect children
            collect_modules(module, depth=depth + 1)

    collect_modules(conf.main_app.vi)

    res = {
        "modules": res,
        # "configuration": dict(conf.admin.items()), # TODO: this could be the short vision, if we use underscores
        "configuration": {
            k.replace("_", "."): v for k, v in conf.admin.items(True)
        }
    }

    return json.dumps(res, cls=CustomJsonEncoder)


@exposed
def getVersion(*args, **kwargs):
    """
    Returns viur-core version number
    """
    version = conf.version

    # always fill up to 4 parts
    while len(version) < 4:
        version += (None,)

    if conf.instance.is_dev_server \
            or ((cuser := current.user.get()) and ("root" in cuser["access"] or "admin" in cuser["access"])):
        return json.dumps(version[:4])

    # Hide patch level + appendix to non-authorized users
    return json.dumps((version[0], version[1], None, None))


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
def get_settings():
    """
    Get public admin-tool specific settings, requires no user to be logged in.
    This is used by new vi-admin.
    """
    fields = {k.replace("_", "."): v for k, v in conf.admin.items(True)}

    if conf.user.google_client_id:
        fields["admin.user.google.clientID"] = conf.user.google_client_id

    return json.dumps(fields, cls=CustomJsonEncoder)


def canAccess(*args, **kwargs) -> bool:
    """
    General access restrictions for the vi-render.
    """

    if (cuser := current.user.get()) and any(right in cuser["access"] for right in ("root", "admin")):
        return True

    return any(fnmatch.fnmatch(current.request.get().path, pat) for pat in conf.security.admin_allowed_paths)


def _postProcessAppObj(obj):
    obj["skey"] = json_render_skey
    obj["timestamp"] = timestamp
    obj["config"] = dumpConfig
    obj["settings"] = get_settings
    obj["getStructure"] = getStructure
    obj["setLanguage"] = setLanguage
    obj["getVersion"] = getVersion
    obj["index"] = index

    # So nicely solved...
    obj["canAccess"] = canAccess
    obj["initialize"] = initialize
    return obj
