"""
ViUR-core
Copyright © 2024 Mausbrand Informationssysteme GmbH

https://core.docs.viur.dev
Licensed under the MIT license. See LICENSE for more information.
"""

import os
import sys

# Set a dummy project id to survive API Client initializations
if sys.argv[0].endswith("viur-core-migrate-config"):
    os.environ["GOOGLE_CLOUD_PROJECT"] = "dummy"

import inspect
import warnings
from types import ModuleType
import typing as t
from google.appengine.api import wrap_wsgi_app

from viur.core import i18n, request, utils
from viur.core.config import conf
from viur.core.decorators import *
from viur.core.decorators import access, exposed, force_post, force_ssl, internal_exposed, skey
from viur.core.module import Method, Module
from viur.core.module import Module, Method
from viur.core.tasks import TaskHandler, runStartupTasks
from .i18n import translate
from .tasks import (DeleteEntitiesIter, PeriodicTask, QueryIter, StartupTask,
                    TaskHandler, callDeferred, retry_n_times, runStartupTasks)

# noinspection PyUnresolvedReferences
from viur.core import logging as viurLogging  # unused import, must exist, initializes request logging

import logging  # this import has to stay here, see #571

__all__ = [
    # basics from this __init__
    "setDefaultLanguage",
    "setDefaultDomainLanguage",
    "setup",
    # prototypes
    "Module",
    "Method",
    # tasks
    "DeleteEntitiesIter",
    "QueryIter",
    "retry_n_times",
    "callDeferred",
    "StartupTask",
    "PeriodicTask",
    # Decorators
    "access",
    "exposed",
    "force_post",
    "force_ssl",
    "internal_exposed",
    "skey",
    # others
    "conf",
    "translate",
]

# Show DeprecationWarning from the viur-core
warnings.filterwarnings("always", category=DeprecationWarning, module=r"viur\.core.*")


def setDefaultLanguage(lang: str):
    """
        Sets the default language used by ViUR to *lang*.

        :param lang: Name of the language module to use by default.
    """
    conf.i18n.default_language = lang.lower()


def setDefaultDomainLanguage(domain: str, lang: str):
    """
        If conf.i18n.language_method is set to "domain", this function allows setting the map of which domain
        should use which language.
        :param domain: The domain for which the language should be set
        :param lang: The language to use (in ISO2 format, e.g. "DE")
    """
    host = domain.lower().strip(" /")
    if host.startswith("www."):
        host = host[4:]
    conf.i18n.domain_language_mapping[host] = lang.lower()


def __build_app(modules: ModuleType | object, renderers: ModuleType | object, default: str = None) -> Module:
    """
        Creates the application-context for the current instance.

        This function converts the classes found in the *modules*-module,
        and the given renders into the object found at ``conf.main_app``.

        Every class found in *modules* becomes

        - instanced
        - get the corresponding renderer attached
        - will be attached to ``conf.main_app``

        :param modules: Usually the module provided as *modules* directory within the application.
        :param renderers: Usually the module *viur.core.renders*, or a dictionary renderName => renderClass.
        :param default: Name of the renderer, which will form the root of the application.
            This will be the renderer, which wont get a prefix, usually html.
            (=> /user instead of /html/user)
    """
    if not isinstance(renderers, dict):
        # build up the dict from viur.core.render
        renderers, renderers_root = {}, renderers
        for key, module in vars(renderers_root).items():
            if "__" not in key:
                renderers[key] = {}
                for subkey, render in vars(module).items():
                    if "__" not in subkey:
                        renderers[key][subkey] = render
        del renderers_root

    # assign ViUR system modules
    from viur.core.modules.moduleconf import ModuleConf  # noqa: E402 # import works only here because circular imports
    from viur.core.modules.script import Script  # noqa: E402 # import works only here because circular imports
    from viur.core.modules.translation import Translation  # noqa: E402 # import works only here because circular imports
    from viur.core.prototypes.instanced_module import InstancedModule  # noqa: E402 # import works only here because circular imports

    modules._tasks = TaskHandler
    modules._moduleconf = ModuleConf
    modules._translation = Translation
    modules.script = Script

    # Resolver defines the URL mapping
    resolver = {}

    # Index is mapping all module instances for global access
    index = (modules.index if hasattr(modules, "index") else Module)("index", "")
    index.register(resolver, renderers[default]["default"](parent=index))

    for module_name, module_cls in vars(modules).items():  # iterate over all modules
        if module_name == "index":
            continue  # ignore index, as it has been processed before!

        if module_name in renderers:
            raise NameError(f"Cannot name module {module_name!r}, as it is a reserved render's name")

        if not (  # we define the cases we want to use and then negate them all
            (inspect.isclass(module_cls) and issubclass(module_cls, Module)  # is a normal Module class
             and not issubclass(module_cls, InstancedModule))  # but not a "instantiable" Module
            or isinstance(module_cls, InstancedModule)  # is an already instanced Module
        ):
            continue

        # remember module_instance for default renderer.
        module_instance = default_module_instance = None

        for render_name, render in renderers.items():  # look, if a particular renderer should be built
            # Only continue when module_cls is configured for this render
            # todo: VIUR4 this is for legacy reasons, can be done better!
            if not getattr(module_cls, render_name, False):
                continue

            # Create a new module instance
            module_instance = module_cls(
                module_name, ("/" + render_name if render_name != default else "") + "/" + module_name
            )

            # Attach the module-specific or the default render
            if render_name == default:  # default or render (sub)namespace?
                default_module_instance = module_instance
                target = resolver
            else:
                if getattr(index, render_name, True) is True:
                    # Render is not build yet, or it is just the simple marker that a given render should be build
                    setattr(index, render_name, Module(render_name, "/" + render_name))

                # Attach the module to the given renderer node
                setattr(getattr(index, render_name), module_name, module_instance)
                target = resolver.setdefault(render_name, {})

            module_instance.register(target, render.get(module_name, render["default"])(parent=module_instance))

            # Apply Renderers postProcess Filters
            if "_postProcessAppObj" in render:  # todo: This is ugly!
                render["_postProcessAppObj"](target)

        # Ugly solution, but there is no better way to do it in ViUR 3:
        # Allow that any module can be accessed by `conf.main_app.<modulename>`,
        # either with default render or the last created render.
        # This behavior does NOT influence the routing.
        if default_module_instance or module_instance:
            setattr(index, module_name, default_module_instance or module_instance)

    # fixme: Below is also ugly...
    if default in renderers and hasattr(renderers[default]["default"], "renderEmail"):
        conf.emailRenderer = renderers[default]["default"]().renderEmail
    elif "html" in renderers:
        conf.emailRenderer = renderers["html"]["default"]().renderEmail

    # This might be useful for debugging, please keep it for now.
    if conf.debug.trace:
        import pprint
        logging.debug(pprint.pformat(resolver))

    conf.main_resolver = resolver
    conf.main_app = index


def setup(modules:  ModuleType | object, render:  ModuleType | object = None, default: str = "html"):
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
    if conf.instance.project_id not in conf.valid_application_ids:
        raise RuntimeError(
            f"""Refusing to start, {conf.instance.project_id=} is not in {conf.valid_application_ids=}""")
    if not render:
        import viur.core.render
        render = viur.core.render

    __build_app(modules, render, default)

    # Send warning email in case trace is activated in a cloud environment
    if ((conf.debug.trace
            or conf.debug.trace_external_call_routing
            or conf.debug.trace_internal_call_routing)
            and (not conf.instance.is_dev_server or conf.debug.dev_server_cloud_logging)):
        from viur.core import email
        try:
            email.sendEMailToAdmins(
                "Debug mode enabled",
                "ViUR just started a new Instance with call tracing enabled! This might log sensitive information!"
            )
        except Exception as exc:  # OverQuota, whatever
            logging.exception(exc)
    # Ensure that our Content Security Policy Header Cache gets build
    from viur.core import securityheaders
    securityheaders._rebuildCspHeaderCache()
    securityheaders._rebuildPermissionHeaderCache()
    setSystemInitialized()
    # Assert that all security related headers are in a sane state
    if conf.security.content_security_policy and conf.security.content_security_policy["_headerCache"]:
        for k in conf.security.content_security_policy["_headerCache"]:
            if not k.startswith("Content-Security-Policy"):
                raise AssertionError("Got unexpected header in "
                                     "conf.security.content_security_policy['_headerCache']")
    if conf.security.strict_transport_security:
        if not conf.security.strict_transport_security.startswith("max-age"):
            raise AssertionError("Got unexpected header in conf.security.strict_transport_security")
    crossDomainPolicies = {None, "none", "master-only", "by-content-type", "all"}
    if conf.security.x_permitted_cross_domain_policies not in crossDomainPolicies:
        raise AssertionError("conf.security.x_permitted_cross_domain_policies "
                             f"must be one of {crossDomainPolicies!r}")
    if conf.security.x_frame_options is not None and isinstance(conf.security.x_frame_options, tuple):
        mode, uri = conf.security.x_frame_options
        assert mode in ["deny", "sameorigin", "allow-from"]
        if mode == "allow-from":
            assert uri is not None and (uri.lower().startswith("https://") or uri.lower().startswith("http://"))
    runStartupTasks()  # Add a deferred call to run all queued startup tasks
    i18n.initializeTranslations()
    if conf.file_hmac_key is None:
        from viur.core import db
        key = db.Key("viur-conf", "viur-conf")
        if not (obj := db.Get(key)):  # create a new "viur-conf"?
            logging.info("Creating new viur-conf")
            obj = db.Entity(key)

        if "hmacKey" not in obj:  # create a new hmacKey
            logging.info("Creating new hmacKey")
            obj["hmacKey"] = utils.string.random(length=20)
            db.Put(obj)

        conf.file_hmac_key = bytes(obj["hmacKey"], "utf-8")

    if conf.instance.is_dev_server:
        WIDTH = 80  # defines the standard width
        FILL = "#"  # define sthe fill char (must be len(1)!)
        PYTHON_VERSION = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)

        # define lines to show
        lines = (
            " LOCAL DEVELOPMENT SERVER IS UP AND RUNNING ",  # title line
            f"""project = \033[1;31m{conf.instance.project_id}\033[0m""",
            f"""python = \033[1;32m{".".join((str(i) for i in PYTHON_VERSION))}\033[0m""",
            f"""viur = \033[1;32m{".".join((str(i) for i in conf.version))}\033[0m""",
            ""  # empty line
        )

        # first and last line are shown with a cool line made of FILL
        first_last = (0, len(lines) - 1)

        # dump to console
        for i, line in enumerate(lines):
            print(
                f"""\033[0m{FILL}{line:{
                    FILL if i in first_last else " "}^{(WIDTH - 2) + (11 if i not in first_last else 0)
                }}{FILL}"""
            )

    return wrap_wsgi_app(app)


def app(environ: dict, start_response: t.Callable):
    return request.Router(environ).response(environ, start_response)


# DEPRECATED ATTRIBUTES HANDLING

__DEPRECATED_DECORATORS = {
    # stuff prior viur-core < 3.5
    "forcePost": ("force_post", force_post),
    "forceSSL": ("force_ssl", force_ssl),
    "internalExposed": ("internal_exposed", internal_exposed)
}


def __getattr__(attr: str) -> object:
    if entry := __DEPRECATED_DECORATORS.get(attr):
        func = entry[1]
        msg = f"@{attr} was replaced by @{entry[0]}"
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        logging.warning(msg, stacklevel=2)
        return func

    return super(__import__(__name__).__class__).__getattr__(attr)
