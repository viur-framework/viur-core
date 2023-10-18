import datetime
import hashlib
import logging
import os
import warnings
from pathlib import Path
from typing import Any, Iterator, Union

import google.auth

from viur.core.version import __version__


class ViurDeprecationsWarning(UserWarning):
    """Class for warnings about deprecated viur-core features."""
    pass


class ConfigType:
    _mapping = {}
    _parent = None

    def __init__(self, *,
                 strict_mode: bool = None,
                 parent: Union["ConfigType", None] = None):
        super().__init__()
        self._strict_mode = strict_mode
        self._parent = parent

    @property
    def _path(self):
        if self._parent is None:
            return ""
        return f"{self._parent._path}{self.__class__.__name__.lower()}."

    @property
    def strict_mode(self):
        # logging.debug(f"{self.__class__=} // {self._parent=} // {self._strict_mode=}")
        if self._strict_mode is not None or self._parent is None:
            # This config has an explicit value set or there's no parent
            return self._strict_mode
        else:
            # no value set: inherit from the parent
            return self._parent.strict_mode

    @strict_mode.setter
    def strict_mode(self, value: bool | None):
        if not isinstance(value, (bool, type(None))):
            raise TypeError(f"Invalid {value=} for strict mode!")
        self._strict_mode = value

    def _resolve_mapping(self, key):
        if key in self._mapping:
            old, key = key, self._mapping[key]
            warnings.warn(f"Conf member {old} is now {key}!",
                          ViurDeprecationsWarning, stacklevel=3)
        return key

    def items(self,
              full_path: bool = False,
              recursive: bool = True,
              ) -> Iterator[tuple[str, Any]]:
        """Get all members.

        :param full_path: Show prefix oder only the key.
        :param recursive: Call .items() on ConfigType members?
        :return:
        """
        # print(self, self.__dict__, vars(self), dir(self))
        for key in dir(self):
            # print(f"{key = }")
            if key in {"_parent", "_strict_mode"}:  # TODO: use .startswith("_") ???
                continue
            value = getattr(self, key)
            # print(f"{key = }, {value = }")
            # if key.startswith("_"):  # TODO: use .startswith("_") ???
            #     continue
            if recursive and isinstance(value, ConfigType):
                yield from value.items(full_path, recursive)
            elif key not in dir(ConfigType):
                if full_path:
                    yield f"{self._path}{key}", value
                else:
                    yield key, value
            # else:
            #     print(f">>> Skip {key}")
            pass  # keep this indent

    def get(self, key, default: Any = None) -> Any:
        """Return an item from the config, if it doesn't exist `default` is returned."""
        if self.strict_mode:
            raise SyntaxError(
                f"In strict mode, the config must not be accessed "
                f"with .get(). Only attribute access is allowed."
            )

        try:
            return self[key]
        except (KeyError, AttributeError):
            return default

    def __getitem__(self, key: str) -> Any:
        """Support the old dict Syntax (getter)."""
        # print(f"CALLING __getitem__({self.__class__}, {key})")

        warnings.warn(f"conf uses now attributes! "
                      f"Use conf.{self._path}{key} to access your option",
                      ViurDeprecationsWarning)

        if self.strict_mode:
            raise SyntaxError(
                f"In strict mode, the config must not be accessed "
                f"with dict notation. Only attribute access is allowed."
            )

        # VIUR3.3: Handle deprecations...
        match key:
            case "viur.downloadUrlFor.expiration":
                msg = f"{key!r} was substituted by `viur.render.html.downloadUrlExpiration`"
                warnings.warn(msg, ViurDeprecationsWarning, stacklevel=3)
                key = "viur.render.html.downloadUrlExpiration"

        # print(f"PASS to getattr({key!r})")
        return getattr(self, key)

    def __getattr__(self, key: str) -> Any:
        # print(f"CALLING __getattr__({self.__class__}, {key})")

        key = self._resolve_mapping(key)

        # Got an old dict-key and resolve the segment to the first dot (.) as attribute.
        if "." in key:
            # print(f"FOUND . in {key = }")
            first, remaining = key.split(".", 1)
            return getattr(getattr(self, first), remaining)

        return super().__getattribute__(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Support the old dict Syntax (setter)."""
        # print(f"CALLING __setitem__({self.__class__}, {key}, {value})")

        if self.strict_mode:
            raise SyntaxError(
                f"In strict mode, the config must not be accessed "
                f"with dict notation. Only attribute access is allowed."
            )

        # VIUR3.3: Handle deprecations...
        match key:
            case "viur.downloadUrlFor.expiration":
                raise ValueError(f"{key!r} was replaced by `viur.render.html.downloadUrlExpiration`, please fix!")

        # TODO: re-enable?!
        # Avoid to set conf values to something which is already the default
        # if key in self and self[key] == value:
        #     msg = f"Setting conf[\"{key}\"] to {value!r} has no effect, as this value has already been set"
        #     warnings.warn(msg, stacklevel=3)
        #     logging.warning(msg, stacklevel=3)
        #     return

        key = self._resolve_mapping(key)

        # Got an old dict-key and resolve the segment to the first dot (.) as attribute.
        if "." in key:
            # print(f"FOUND . in {key = }")
            first, remaining = key.split(".", 1)
            if not hasattr(self, first):
                # TODO: Compatibility, remove it in a future major release!
                #       This segment doesn't exist. Create it
                logging.warning(f"Creating new type for {first}")
                setattr(self, first, type(first.capitalize(), (ConfigType,), {})())
            getattr(self, first)[remaining] = value
            return

        return setattr(self, key, value)

    def __setattr__(self, key: str, value: Any) -> None:
        # print(f"CALLING __setattr__({self.__class__}, {key}, {value})")

        key = self._resolve_mapping(key)

        # Got an old dict-key and resolve the segment to the first dot (.) as attribute.
        if "." in key:
            # print(f"FOUND . in {key = }")
            first, remaining = key.split(".", 1)
            return setattr(getattr(self, first), remaining, value)

        return super().__setattr__(key, value)

    def __repr__(self):
        return f"{self.__class__.__qualname__}({dict(self.items(False, False))})"


# Some values used more than once below
_project_id = google.auth.default()[1]
_app_version = os.getenv("GAE_VERSION")

# Determine our basePath (as os.getCWD is broken on appengine)
_project_base_path = Path().absolute()
_core_base_path = Path(__file__).parent.parent.parent  # fixme: this points to site-packages!!!


# Conf is a static, local dictionary.
# Changes here apply locally to the current instance only.


class Admin(ConfigType):
    """Administration tool configuration"""

    name = "ViUR"
    """Administration tool configuration"""

    logo = ""
    """URL for the Logo in the Topbar of the VI"""

    login_background = ""
    """URL for the big Image in the background of the VI Login screen"""

    login_logo = ""
    """URL for the Logo over the VI Login screen"""

    color_primary = "#d00f1c"
    """primary color for the  VI"""

    color_secondary = "#333333"
    """secondary color for the  VI"""

    _mapping = {
        "login.background": "login_background",
        "login.logo": "login_logo",
        "color.primary": "color_primary",
        "color.secondary": "color_secondary",
    }


class Viur(ConfigType):
    accessRights = ["root", "admin"]
    """Additional access rights available on this project"""

    availableLanguages = ["en"]
    """List of language-codes, which are valid for this application"""

    bone_boolean_str2true = ("true", "yes", "1")
    """Allowed values that define a str to evaluate to true"""

    cacheEnvironmentKey = None
    """If set, this function will be called for each cache-attempt
    and the result will be included in the computed cache-key"""

    compatibility = [
        "json.bone.structure.camelcasenames",  # use camelCase attribute names (see #637 for details)
        "bone.structure.keytuples",  # use classic structure notation: `"structure = [["key", {...}] ...]` (#649)
        "json.bone.structure.inlists",  # dump skeleton structure with every JSON list response (#774 for details)
    ]
    """Backward compatibility flags; Remove to enforce new layout."""

    contentSecurityPolicy = None
    """If set, viur will emit a CSP http-header with each request. Use the csp module to set this property"""

    db_engine = "viur.datastore"
    """Database engine module"""

    defaultLanguage = "en"
    """Unless overridden by the Project: Use english as default language"""

    domainLanguageMapping = {}
    """Maps Domains to alternative default languages"""

    email_logRetention = datetime.timedelta(days=30)
    """For how long we'll keep successfully send emails in the viur-emails table"""

    email_transportClass = None
    """Class that actually delivers the email using the service provider
    of choice. See email.py for more details
    """

    email_sendFromLocalDevelopmentServer = False
    """If set, we'll enable sending emails from the local development server.
    Otherwise, they'll just be logged.
    """

    email_recipientOverride = None
    """If set, all outgoing emails will be sent to this address
    (overriding the 'dests'-parameter in email.sendEmail)
    """

    email_senderOverride = None
    """If set, this sender will be used, regardless of what the templates advertise as sender"""

    email_admin_recipients = None
    """Sets recipients for mails send with email.sendEMailToAdmins. If not set, all root users will be used."""

    errorHandler = None
    """If set, ViUR calls this function instead of rendering the viur.errorTemplate if an exception occurs"""

    static_embedSvg_path = "/static/svgs/"
    """Path to the static SVGs folder. Will be used by the jinja-renderer-method: embedSvg"""

    forceSSL = True
    """If true, all requests must be encrypted (ignored on development server)"""

    file_hmacKey = None
    """Hmac-Key used to sign download urls - set automatically"""

    file_derivers = {}
    """Call-Map for file pre-processors"""

    file_thumbnailer_url = None
    # TODO: """docstring"""

    instance_app_version = _app_version
    """Name of this version as deployed to the appengine"""

    instance_core_base_path = _core_base_path
    """The base path of the core, can be used to find file in the core folder"""

    instance_is_dev_server = os.getenv("GAE_ENV") == "localdev"
    """Determine whether instance is running on a local development server"""

    instance_project_base_path = _project_base_path
    """The base path of the project, can be used to find file in the project folder"""

    instance_project_id = _project_id
    """The instance's project ID"""

    instance_version_hash = hashlib.sha256((_app_version + _project_id).encode("UTF-8")).hexdigest()[:10]
    """Version hash that does not reveal the actual version name, can be used for cache-busting static resources"""

    languageAliasMap = {}
    """Allows mapping of certain languages to one translation (ie. us->en)"""

    languageMethod = "session"
    """Defines how translations are applied:
        - session: Per Session
        - url: inject language prefix in url
        - domain: one domain per language
    """

    languageModuleMap = {}
    """Maps modules to their translation (if set)"""

    logMissingTranslations = False  # TODO: move to debug
    """If true, ViUR will log missing translations in the datastore"""

    mainApp = None
    """Reference to our pre-build Application-Instance"""

    mainResolver = None
    """Dictionary for Resolving functions for URLs"""

    maxPasswordLength = 512
    """Prevent Denial of Service attacks using large inputs for pbkdf2"""

    maxPostParamsCount = 250
    """Upper limit of the amount of parameters we accept per request. Prevents Hash-Collision-Attacks"""

    moduleconf_admin_info = {
        "icon": "icon-settings",
        "display": "hidden",
    }
    """Describing the internal ModuleConfig-module"""

    script_admin_info = { # TODO: not in use?!
        "icon": "icon-hashtag",
        "display": "hidden",
    }

    noSSLCheckUrls = ["/_tasks*", "/ah/*"]
    """List of URLs for which viur.forceSSL is ignored.
    Add an asterisk to mark that entry as a prefix (exact match otherwise)"""

    otp_issuer = None
    """The name of the issuer for the opt token"""

    render_html_downloadUrlExpiration = None
    """The default duration, for which downloadURLs generated by the html renderer will stay valid"""

    render_json_downloadUrlExpiration = None
    """The default duration, for which downloadURLs generated by the json renderer will stay valid"""

    requestPreprocessor = None
    """Allows the application to register a function that's called before the request gets routed"""

    searchValidChars = "abcdefghijklmnopqrstuvwxyzäöüß0123456789"
    """Characters valid for the internal search functionality (all other chars are ignored)"""

    session_lifeTime = 60 * 60
    """Default is 60 minutes lifetime for ViUR sessions"""

    session_persistentFieldsOnLogin = ["language"]
    """If set, these Fields will survive the session.reset() called on user/login"""

    session_persistentFieldsOnLogout = ["language"]
    """If set, these Fields will survive the session.reset() called on user/logout"""

    skeleton_search_path = [
        "/skeletons/",  # skeletons of the project
        "/viur/core/",  # system-defined skeletons of viur-core
        "/viur-core/core/"  # system-defined skeletons of viur-core, only used by editable installation
    ]
    """Priority, in which skeletons are loaded"""

    tasks_customEnvironmentHandler = None
    """If set, must be a tuple of two functions serializing/restoring
    additional environmental data in deferred requests
    """

    user_roles = {
        "custom": "Custom",
        "user": "User",
        "viewer": "Viewer",
        "editor": "Editor",
        "admin": "Administrator",
    }
    """User roles available on this project"""

    user_google_client_id = None
    """OAuth Client ID for Google Login"""

    validApplicationIDs = []
    """Which application-ids we're supposed to run on"""

    version = tuple(int(part) if part.isdigit() else part for part in __version__.split(".", 3))
    """Semantic version number of viur-core as a tuple of 3 (major, minor, patch-level)"""

    viur2import_blobsource = None

    _mapping = {
        "bone.boolean.str2true": "bone_boolean_str2true",
        "db.engine": "db_engine",
        "email.logRetention": "email_logRetention",
        "email.transportClass": "email_transportClass",
        "email.sendFromLocalDevelopmentServer": "email_sendFromLocalDevelopmentServer",
        "email.recipientOverride": "email_recipientOverride",
        "email.senderOverride": "email_senderOverride",
        "email.admin_recipients": "email_admin_recipients",
        "static.embedSvg.path": "static_embedSvg_path",
        "file.hmacKey": "file_hmacKey",
        "file.derivers": "file_derivers",
        "file.thumbnailerURL": "file_thumbnailer_url",
        "instance.app_version": "instance_app_version",
        "instance.core_base_path": "instance_core_base_path",
        "instance.is_dev_server": "instance_is_dev_server",
        "instance.project_base_path": "instance_project_base_path",
        "instance.project_id": "instance_project_id",
        "instance.version_hash": "instance_version_hash",
        "moduleconf.admin_info": "moduleconf_admin_info",
        "script.admin_info": "script_admin_info",
        "render.html.downloadUrlExpiration": "render_html_downloadUrlExpiration",
        "render.json.downloadUrlExpiration": "render_json_downloadUrlExpiration",
        "session.lifeTime": "session_lifeTime",
        "session.persistentFieldsOnLogin": "session_persistentFieldsOnLogin",
        "session.persistentFieldsOnLogout": "session_persistentFieldsOnLogout",
        "skeleton.searchPath": "skeleton_search_path",
        "tasks.customEnvironmentHandler": "tasks_customEnvironmentHandler",
        "user.roles": "user_roles",
        "user.google.clientID": "user_google_client_id",
        "user.google.gsuiteDomains": "user_google_gsuiteDomains",
        "viur2import.blobsource": "viur2import_blobsource",
        "otp.issuer": "otp_issuer",
    }


class Security(ConfigType):
    contentSecurityPolicy = {
        "enforce": {
            "style-src": ["self", "https://accounts.google.com/gsi/style"],
            "default-src": ["self"],
            "img-src": ["self", "storage.googleapis.com"],  # Serving-URLs of file-Bones will point here
            "script-src": ["self", "https://accounts.google.com/gsi/client"],
            # Required for login with Google
            "frame-src": ["self", "www.google.com", "drive.google.com", "accounts.google.com"],
            "form-action": ["self"],
            "connect-src": ["self", "accounts.google.com"],
            "upgrade-insecure-requests": [],
            "object-src": ["none"],
        }
    }
    """If set, viur will emit a CSP http-header with each request. Use security.addCspRule to set this property"""

    referrerPolicy = "strict-origin"
    """Per default, we'll emit Referrer-Policy: strict-origin so no referrers leak to external services"""

    permissionsPolicy = {
        "autoplay": ["self"],
        "camera": [],
        "display-capture": [],
        "document-domain": [],
        "encrypted-media": [],
        "fullscreen": [],
        "geolocation": [],
        "microphone": [],
        "publickey-credentials-get": [],
        "usb": [],
    }
    """Include a default permissions-policy.
    To use the camera or microphone, you'll have to call
    :meth: securityheaders.setPermissionPolicyDirective to include at least "self"
    """

    enableCOEP = False
    """Shall we emit Cross-Origin-Embedder-Policy: require-corp?"""

    enableCOOP = "same-origin"
    """Emit a Cross-Origin-Opener-Policy Header?
    Valid values are same-origin|same-origin-allow-popups|unsafe-none"""

    enableCORP = "same-origin"
    """Emit a Cross-Origin-Resource-Policy Header?
    Valid values are same-site|same-origin|cross-origin"""

    strictTransportSecurity = "max-age=22118400"
    """If set, ViUR will emit a HSTS HTTP-header with each request.
    Use security.enableStrictTransportSecurity to set this property"""

    xFrameOptions = ("sameorigin", None)
    """If set, ViUR will emit an X-Frame-Options header,"""

    xXssProtection = True
    """ViUR will emit an X-XSS-Protection header if set (the default),"""

    xContentTypeOptions = True
    """ViUR will emit X-Content-Type-Options: nosniff Header unless set to False"""

    xPermittedCrossDomainPolicies = "none"
    """Unless set to logical none; ViUR will emit a X-Permitted-Cross-Domain-Policies with each request"""

    captcha_defaultCredentials = None
    """The default sitekey and secret to use for the captcha-bone.
    If set, must be a dictionary of "sitekey" and "secret".
    """

    password_recovery_key_length = 42
    """Length of the Password recovery key"""

    _mapping = {
        "captcha.defaultCredentials": "captcha_defaultCredentials",
    }


class Debug(ConfigType):
    trace = False
    """If enabled, trace any routing, HTTPExceptions and decorations for debugging and insight"""
    traceExceptions = False
    """If enabled, user-generated exceptions from the viur.core.errors module won't be caught and handled"""
    traceExternalCallRouting = False
    """If enabled, ViUR will log which (exposed) function are called from outside with what arguments"""
    traceInternalCallRouting = False
    """If enabled, ViUR will log which (internal-exposed) function are called from templates with what arguments"""
    skeleton_fromClient = False
    """If enabled, log errors raises from skeleton.fromClient()"""

    dev_server_cloud_logging = False
    """If disabled the local logging will not send with requestLogger to the cloud"""

    disableCache = False
    """If set to true, the decorator @enableCache from viur.core.cache has no effect"""

    _mapping = {
        "skeleton.fromClient": "skeleton_fromClient",
    }


class Conf(ConfigType):
    """
    Conf class wraps the conf dict and allows to handle deprecated keys or other special operations.
    """

    def __init__(self, strict_mode: bool = False):
        super().__init__()
        self._strict_mode = strict_mode
        self.admin = Admin(parent=self)
        self.viur = Viur(parent=self)
        self.security = Security(parent=self)
        self.debug = Debug(parent=self)

    _mapping = {
        "viur.dev_server_cloud_logging": "debug.dev_server_cloud_logging",
        "viur.disableCache": "debug.disableCache",
    }

    def _resolve_mapping(self, key):
        if key.startswith("viur.security"):
            key = key.replace("viur.security.", "security.")
        if key.startswith("viur.debug"):
            key = key.replace("viur.debug.", "debug.")
        return super()._resolve_mapping(key)


# from viur.core import utils

conf = Conf(
    strict_mode=os.getenv("VIUR_CORE_CONFIG_STRICT_MODE", "").lower() == "true",
)

print(os.getenv("CONFIG_STRICT_MODE"))
print(os.environ)

from pprint import pprint  # noqa

# pprint(conf)
# for k,v in conf.items():
#     print(f"{k} = {v}")
# print("# DUMP IT!")
pprint(dict(conf.items()))
pprint(dict(conf.items(True)))
# print("## REPRESENT YOURSELF!")
# print(repr(conf))
# print("# PPRINT")
print(pprint(conf))

# import viur.core.utils
