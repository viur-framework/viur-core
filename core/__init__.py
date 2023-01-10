"""
                 iii
                iii
               iii

           vvv iii uu      uu rrrrrrrr
          vvvv iii uu      uu rr     rr
  v      vvvv  iii uu      uu rr     rr
  vv    vvvv   iii uu      uu rr rrrrr
 vvvv  vvvv    iii uu      uu rr rrr
  vvv vvvv     iii uu      uu rr  rrr
   vvvvvv      iii  uu    uu  rr   rrr
    vvvv       iii   uuuuuu   rr    rrr

   I N F O R M A T I O N    S Y S T E M

 ViUR core
 Copyright (C) 2012-2023 by Mausbrand Informationssysteme GmbH

 ViUR is a free software development framework for the Google App Engine™.
 More about ViUR can be found at https://www.viur.dev.

 Licensed under the GNU Lesser General Public License, version 3.
 See file LICENSE for more information.
"""

import os
import webob
import yaml
from types import ModuleType
from typing import Callable, Dict, Union, List
from viur.core import session, errors, i18n, request, utils
from viur.core.config import conf
from viur.core.tasks import TaskHandler, runStartupTasks
from viur.core import logging as viurLogging  # Initialize request logging
import logging  # this import has to stay here, see #571


def load_indexes_from_file() -> Dict[str, List]:
    """
        Loads all indexes from the index.yaml and stores it in a dictionary  sorted by the module(kind)
        :return A dictionary of indexes per module
    """
    indexes_dict = {}
    try:
        with open(os.path.join(utils.projectBasePath, "index.yaml"), "r") as file:
            indexes = yaml.safe_load(file)
            indexes = indexes.get("indexes", [])
            for index in indexes:
                index["properties"] = [_property["name"] for _property in index["properties"]]
                indexes_dict.setdefault(index["kind"], []).append(index)

    except FileNotFoundError:
        logging.warning("index.yaml not found")
        return {}

    return indexes_dict


def setDefaultLanguage(lang: str):
    """
        Sets the default language used by ViUR to *lang*.

        :param lang: Name of the language module to use by default.
    """
    conf["viur.defaultLanguage"] = lang.lower()


def setDefaultDomainLanguage(domain: str, lang: str):
    """
        If conf["viur.languageMethod"] is set to "domain", this function allows setting the map of which domain
        should use which language.
        :param domain: The domain for which the language should be set
        :param lang: The language to use (in ISO2 format, e.g. "DE")
    """
    host = domain.lower().strip(" /")
    if host.startswith("www."):
        host = host[4:]
    conf["viur.domainLanguageMapping"][host] = lang.lower()


def mapModule(moduleObj: object, moduleName: str, targetResolverRender: dict):
    """
        Maps each function that's exposed of moduleObj into the branch of `prop:viur.core.conf["viur.mainResolver"]`
        that's referenced by `prop:targetResolverRender`. Will also walk `prop:_viurMapSubmodules` if set
        and map these sub-modules also.
    """
    moduleFunctions = {}
    for key in [x for x in dir(moduleObj) if x[0] != "_"]:
        prop = getattr(moduleObj, key)
        if key == "canAccess" or getattr(prop, "exposed", None):
            moduleFunctions[key] = prop
    for lang in conf["viur.availableLanguages"] or [conf["viur.defaultLanguage"]]:
        # Map the module under each translation
        if "seoLanguageMap" in dir(moduleObj) and lang in moduleObj.seoLanguageMap:
            translatedModuleName = moduleObj.seoLanguageMap[lang]
            if translatedModuleName not in targetResolverRender:
                targetResolverRender[translatedModuleName] = {}
            for fname, fcall in moduleFunctions.items():
                targetResolverRender[translatedModuleName][fname] = fcall
                # Map translated function names
                if getattr(fcall, "seoLanguageMap", None) and lang in fcall.seoLanguageMap:
                    targetResolverRender[translatedModuleName][fcall.seoLanguageMap[lang]] = fcall
            if "_viurMapSubmodules" in dir(moduleObj):
                # Map any Functions on deeper nested function
                subModules = moduleObj._viurMapSubmodules
                for subModule in subModules:
                    obj = getattr(moduleObj, subModule, None)
                    if obj:
                        mapModule(obj, subModule, targetResolverRender[translatedModuleName])
    if moduleName == "index":
        targetFunctionLevel = targetResolverRender
    else:
        # Map the module also under it's original name
        if moduleName not in targetResolverRender:
            targetResolverRender[moduleName] = {}
        targetFunctionLevel = targetResolverRender[moduleName]
    for fname, fcall in moduleFunctions.items():
        targetFunctionLevel[fname] = fcall
        # Map translated function names
        if getattr(fcall, "seoLanguageMap", None):
            for translatedFunctionName in fcall.seoLanguageMap.values():
                targetFunctionLevel[translatedFunctionName] = fcall
    if "_viurMapSubmodules" in dir(moduleObj):
        # Map any Functions on deeper nested function
        subModules = moduleObj._viurMapSubmodules
        for subModule in subModules:
            obj = getattr(moduleObj, subModule, None)
            if obj:
                mapModule(obj, subModule, targetFunctionLevel)


def buildApp(modules: Union[ModuleType, object], renderers: Union[ModuleType, Dict], default: str = None):
    """
        Creates the application-context for the current instance.

        This function converts the classes found in the *modules*-module,
        and the given renders into the object found at ``conf["viur.mainApp"]``.

        Every class found in *modules* becomes

        - instanced
        - get the corresponding renderer attached
        - will be attached to ``conf["viur.mainApp"]``

        :param modules: Usually the module provided as *modules* directory within the application.
        :param renderers: Usually the module *viur.core.renders*, or a dictionary renderName => renderClass.
        :param default: Name of the renderer, which will form the root of the application.
            This will be the renderer, which wont get a prefix, usually html.
            (=> /user instead of /html/user)
    """

    class ExtendableObject(object):
        pass

    if not isinstance(renderers, dict):
        # build up the dict from viur.core.render
        renderers, renderRootModule = {}, renderers
        for key, renderModule in vars(renderRootModule).items():
            if "__" not in key:
                renderers[key] = {}
                for subkey, render in vars(renderModule).items():
                    if "__" not in subkey:
                        renderers[key][subkey] = render
        del renderRootModule
    from viur.core.prototypes import BasicApplication  # avoid circular import
    if hasattr(modules, "index"):
        if issubclass(modules.index, BasicApplication):
            root = modules.index("index", "")
        else:
            root = modules.index()  # old style for backward compatibility
    else:
        root = ExtendableObject()
    modules._tasks = TaskHandler
    from viur.core.modules.moduleconf import ModuleConf  # noqa: E402 # import works only here because circular imports
    modules._moduleconf = ModuleConf
    resolverDict = {}
    indexes = load_indexes_from_file()
    for moduleName, moduleClass in vars(modules).items():  # iterate over all modules
        if moduleName == "index":
            mapModule(root, "index", resolverDict)
            if isinstance(root, BasicApplication):
                root.render = renderers[default]["default"](parent=root)
            continue
        for renderName, render in renderers.items():  # look, if a particular render should be built
            if getattr(moduleClass, renderName, False) is True:
                modulePath = "%s/%s" % ("/" + renderName if renderName != default else "", moduleName)
                moduleInstance = moduleClass(moduleName, modulePath)
                # Attach the module-specific or the default render
                moduleInstance.render = render.get(moduleName, render["default"])(parent=moduleInstance)
                moduleInstance.indexes = indexes.get(moduleName, [])
                if renderName == default:  # default or render (sub)namespace?
                    setattr(root, moduleName, moduleInstance)
                    targetResolverRender = resolverDict
                else:
                    if getattr(root, renderName, True) is True:
                        # Render is not build yet, or it is just the simple marker that a given render should be build
                        setattr(root, renderName, ExtendableObject())
                    # Attach the module to the given renderer node
                    setattr(getattr(root, renderName), moduleName, moduleInstance)
                    targetResolverRender = resolverDict.setdefault(renderName, {})
                mapModule(moduleInstance, moduleName, targetResolverRender)
                # Apply Renderers postProcess Filters
                if "_postProcessAppObj" in render:
                    render["_postProcessAppObj"](targetResolverRender)
        if hasattr(moduleClass, "seoLanguageMap"):
            conf["viur.languageModuleMap"][moduleName] = moduleClass.seoLanguageMap
    conf["viur.mainResolver"] = resolverDict

    if conf["viur.debug.traceExternalCallRouting"] or conf["viur.debug.traceInternalCallRouting"]:
        from viur.core import email
        try:
            email.sendEMailToAdmins("Debug mode enabled",
                                    "ViUR just started a new Instance with calltracing enabled! This will log sensitive information!")
        except:  # OverQuota, whatever
            pass  # Dont render this instance unusable
    if default in renderers and hasattr(renderers[default]["default"], "renderEmail"):
        conf["viur.emailRenderer"] = renderers[default]["default"]().renderEmail
    elif "html" in renderers:
        conf["viur.emailRenderer"] = renderers["html"]["default"]().renderEmail

    return root


def setup(modules: Union[object, ModuleType], render: Union[ModuleType, Dict] = None, default: str = "html"):
    """
        Define whats going to be served by this instance.

        :param modules: Usually the module provided as *modules* directory within the application.
        :param render: Usually the module *viur.core.renders*, or a dictionary renderName => renderClass.
        :param default: Name of the renderer, which will form the root of the application.\
            This will be the renderer, which wont get a prefix, usually html. \
            (=> /user instead of /html/user)
    """
    from viur.core.bones.base import setSystemInitialized
    # noinspection PyUnresolvedReferences
    import skeletons  # This import is not used here but _must_ remain to ensure that the
    # application's data models are explicitly imported at some place!
    if conf["viur.instance.project_id"] not in conf["viur.validApplicationIDs"]:
        raise RuntimeError(
            f"""Refusing to start, {conf["viur.instance.project_id"]=} is not in {conf["viur.validApplicationIDs"]=}""")
    if not render:
        import viur.core.render
        render = viur.core.render
    conf["viur.mainApp"] = buildApp(modules, render, default)
    # conf["viur.wsgiApp"] = webapp.WSGIApplication([(r'/(.*)', BrowseHandler)])
    # Ensure that our Content Security Policy Header Cache gets build
    from viur.core import securityheaders
    securityheaders._rebuildCspHeaderCache()
    securityheaders._rebuildPermissionHeaderCache()
    setSystemInitialized()
    # Assert that all security related headers are in a sane state
    if conf["viur.security.contentSecurityPolicy"] and conf["viur.security.contentSecurityPolicy"]["_headerCache"]:
        for k in conf["viur.security.contentSecurityPolicy"]["_headerCache"]:
            if not k.startswith("Content-Security-Policy"):
                raise AssertionError("Got unexpected header in "
                                     "conf['viur.security.contentSecurityPolicy']['_headerCache']")
    if conf["viur.security.strictTransportSecurity"]:
        if not conf["viur.security.strictTransportSecurity"].startswith("max-age"):
            raise AssertionError("Got unexpected header in conf['viur.security.strictTransportSecurity']")
    crossDomainPolicies = {None, "none", "master-only", "by-content-type", "all"}
    if conf["viur.security.xPermittedCrossDomainPolicies"] not in crossDomainPolicies:
        raise AssertionError("conf[\"viur.security.xPermittedCrossDomainPolicies\"] "
                             f"must be one of {crossDomainPolicies!r}")
    if conf["viur.security.xFrameOptions"] is not None and isinstance(conf["viur.security.xFrameOptions"], tuple):
        mode, uri = conf["viur.security.xFrameOptions"]
        assert mode in ["deny", "sameorigin", "allow-from"]
        if mode == "allow-from":
            assert uri is not None and (uri.lower().startswith("https://") or uri.lower().startswith("http://"))
    runStartupTasks()  # Add a deferred call to run all queued startup tasks
    i18n.initializeTranslations()
    if conf["viur.file.hmacKey"] is None:
        from viur.core import db
        key = db.Key("viur-conf", "viur-conf")
        if not (obj := db.Get(key)):  # create a new "viur-conf"?
            logging.info("Creating new viur-conf")
            obj = db.Entity(key)

        if "hmacKey" not in obj:  # create a new hmacKey
            logging.info("Creating new hmacKey")
            obj["hmacKey"] = utils.generateRandomString(length=20)
            db.Put(obj)

        conf["viur.file.hmacKey"] = bytes(obj["hmacKey"], "utf-8")
    return app


def app(environ: dict, start_response: Callable):
    req = webob.Request(environ)
    resp = webob.Response()
    handler = request.BrowseHandler(req, resp)

    # Set context variables
    utils.currentLanguage.set(conf["viur.defaultLanguage"])
    utils.currentRequest.set(handler)
    utils.currentSession.set(session.GaeSession())
    utils.currentRequestData.set({})

    # Handle request
    handler.processRequest()

    # Unset context variables
    utils.currentLanguage.set(None)
    utils.currentRequestData.set(None)
    utils.currentSession.set(None)
    utils.currentRequest.set(None)

    return resp(environ, start_response)


## Decorators ##
def forceSSL(f: Callable) -> Callable:
    """
        Decorator, which forces usage of an encrypted Channel for a given resource.
        Has no effect on development-servers.
    """
    f.forceSSL = True
    return f


def forcePost(f: Callable) -> Callable:
    """
        Decorator, which forces usage of an http post request.
    """
    f.forcePost = True
    return f


def exposed(f: Union[Callable, dict]) -> Callable:
    """
        Decorator, which marks an function as exposed.

        Only exposed functions are callable by http-requests.
        Can optionally receive a dict of language->translated name to make that function
        available under different names
    """
    if isinstance(f, dict):
        # We received said dictionary:
        def exposeWithTranslations(g):
            g.exposed = True
            g.seoLanguageMap = f
            return g

        return exposeWithTranslations
    else:
        f.exposed = True
        f.seoLanguageMap = None
        return f


def internalExposed(f: Callable) -> Callable:
    """
        Decorator, marks an function as internal exposed.

        Internal exposed functions are not callable by external http-requests,
        but can be called by templates using ``execRequest()``.
    """
    f.internalExposed = True
    return f
