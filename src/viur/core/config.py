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
    access_rights = ["root", "admin"]
    """Additional access rights available on this project"""

    available_languages = ["en"]
    """List of language-codes, which are valid for this application"""

    bone_boolean_str2true = ("true", "yes", "1")
    """Allowed values that define a str to evaluate to true"""

    cache_environment_key = None
    """If set, this function will be called for each cache-attempt
    and the result will be included in the computed cache-key"""

    compatibility = [
        "json.bone.structure.camelcasenames",  # use camelCase attribute names (see #637 for details)
        "bone.structure.keytuples",  # use classic structure notation: `"structure = [["key", {...}] ...]` (#649)
        "json.bone.structure.inlists",  # dump skeleton structure with every JSON list response (#774 for details)
    ]
    """Backward compatibility flags; Remove to enforce new layout."""

    db_engine = "viur.datastore"
    """Database engine module"""

    default_language = "en"
    """Unless overridden by the Project: Use english as default language"""

    domain_language_mapping = {}
    """Maps Domains to alternative default languages"""

    # TODO: Email sub type?
    email_log_retention = datetime.timedelta(days=30)
    """For how long we'll keep successfully send emails in the viur-emails table"""

    email_transport_class = None
    """Class that actually delivers the email using the service provider
    of choice. See email.py for more details
    """

    email_send_from_local_development_server = False
    """If set, we'll enable sending emails from the local development server.
    Otherwise, they'll just be logged.
    """

    email_recipient_override = None
    """If set, all outgoing emails will be sent to this address
    (overriding the 'dests'-parameter in email.sendEmail)
    """

    email_sender_override = None
    """If set, this sender will be used, regardless of what the templates advertise as sender"""

    email_admin_recipients = None
    """Sets recipients for mails send with email.sendEMailToAdmins. If not set, all root users will be used."""

    error_handler = None
    """If set, ViUR calls this function instead of rendering the viur.errorTemplate if an exception occurs"""

    static_embed_svg_path = "/static/svgs/"
    """Path to the static SVGs folder. Will be used by the jinja-renderer-method: embedSvg"""

    force_ssl = True
    """If true, all requests must be encrypted (ignored on development server)"""

    file_hmac_key = None
    """Hmac-Key used to sign download urls - set automatically"""

    file_derivers = {}  # FIXME: Is this correct English?
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

    language_alias_map = {}
    """Allows mapping of certain languages to one translation (ie. us->en)"""

    language_method = "session"
    """Defines how translations are applied:
        - session: Per Session
        - url: inject language prefix in url
        - domain: one domain per language
    """

    language_module_map = {}
    """Maps modules to their translation (if set)"""

    log_missing_translations = False  # TODO: move to debug
    """If true, ViUR will log missing translations in the datastore"""

    main_app = None
    """Reference to our pre-build Application-Instance"""

    main_resolver = None
    """Dictionary for Resolving functions for URLs"""

    max_password_length = 512
    """Prevent Denial of Service attacks using large inputs for pbkdf2"""

    max_post_params_count = 250
    """Upper limit of the amount of parameters we accept per request. Prevents Hash-Collision-Attacks"""

    moduleconf_admin_info = {
        "icon": "icon-settings",
        "display": "hidden",
    }
    """Describing the internal ModuleConfig-module"""

    script_admin_info = {
        "icon": "icon-hashtag",
        "display": "hidden",
    }
    """Describing the Script module"""

    no_ssl_check_urls = ["/_tasks*", "/ah/*"]
    """List of URLs for which viur.force_ssl is ignored.
    Add an asterisk to mark that entry as a prefix (exact match otherwise)"""

    otp_issuer = None
    """The name of the issuer for the opt token"""

    render_html_download_url_expiration = None
    """The default duration, for which downloadURLs generated by the html renderer will stay valid"""

    render_json_download_url_expiration = None
    """The default duration, for which downloadURLs generated by the json renderer will stay valid"""

    request_preprocessor = None
    """Allows the application to register a function that's called before the request gets routed"""

    search_valid_chars = "abcdefghijklmnopqrstuvwxyzäöüß0123456789"
    """Characters valid for the internal search functionality (all other chars are ignored)"""

    session_life_time = 60 * 60
    """Default is 60 minutes lifetime for ViUR sessions"""

    session_persistent_fields_on_login = ["language"]
    """If set, these Fields will survive the session.reset() called on user/login"""

    session_persistent_fields_on_logout = ["language"]
    """If set, these Fields will survive the session.reset() called on user/logout"""

    skeleton_search_path = [
        "/skeletons/",  # skeletons of the project
        "/viur/core/",  # system-defined skeletons of viur-core
        "/viur-core/core/"  # system-defined skeletons of viur-core, only used by editable installation
    ]
    """Priority, in which skeletons are loaded"""

    tasks_custom_environment_handler = None
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

    user_google_gsuite_domains = []
    # TODO: """"""

    valid_application_ids = []
    """Which application-ids we're supposed to run on"""

    version = tuple(int(part) if part.isdigit() else part for part in __version__.split(".", 3))
    """Semantic version number of viur-core as a tuple of 3 (major, minor, patch-level)"""

    viur2import_blobsource = None

    _mapping = {
        "accessRights": "access_rights",
        "availableLanguages": "available_languages",
        "cacheEnvironmentKey": "cache_environment_key",
        "contentSecurityPolicy": "content_security_policy",
        "defaultLanguage": "default_language",
        "domainLanguageMapping": "domain_language_mapping",
        "bone.boolean.str2true": "bone_boolean_str2true",
        "db.engine": "db_engine",
        "email.logRetention": "email_log_retention",
        "email.transportClass": "email_transport_class",
        "email.sendFromLocalDevelopmentServer": "email_send_from_local_development_server",
        "email.recipientOverride": "email_recipient_override",
        "email.senderOverride": "email_sender_override",
        "email.admin_recipients": "email_admin_recipients",
        "errorHandler": "error_handler",
        "static.embedSvg.path": "static_embed_svg_path",
        "file.hmacKey": "file_hmac_key",
        "forceSSL": "force_ssl",
        "file_hmacKey": "file_hmac_key",
        "file.derivers": "file_derivers",
        "file.thumbnailerURL": "file_thumbnailer_url",
        "instance.app_version": "instance_app_version",
        "instance.core_base_path": "instance_core_base_path",
        "instance.is_dev_server": "instance_is_dev_server",
        "instance.project_base_path": "instance_project_base_path",
        "instance.project_id": "instance_project_id",
        "instance.version_hash": "instance_version_hash",
        "languageAliasMap": "language_alias_map",
        "languageMethod": "language_method",
        "languageModuleMap": "language_module_map",
        "logMissingTranslations": "log_missing_translations",
        "mainApp": "main_app",
        "mainResolver": "main_resolver",
        "maxPasswordLength": "max_password_length",
        "maxPostParamsCount": "max_post_params_count",
        "moduleconf.admin_info": "moduleconf_admin_info",
        "script.admin_info": "script_admin_info",
        "noSSLCheckUrls": "no_ssl_check_urls",
        "otp.issuer": "otp_issuer",
        "render.html.downloadUrlExpiration": "render_html_download_url_expiration",
        "render.json.downloadUrlExpiration": "render_json_download_url_expiration",
        "requestPreprocessor": "request_preprocessor",
        "searchValidChars": "search_valid_chars",
        "session.lifeTime": "session_life_time",
        "session.persistentFieldsOnLogin": "session_persistent_fields_on_login",
        "session.persistentFieldsOnLogout": "session_persistent_fields_on_logout",
        "skeleton.searchPath": "skeleton_search_path",
        "tasks.customEnvironmentHandler": "tasks_custom_environment_handler",
        "user.roles": "user_roles",
        "user.google.clientID": "user_google_client_id",
        "validApplicationIDs": "valid_application_ids",
        "user.google.gsuiteDomains": "user_google_gsuite_domains",
        "viur2import.blobsource": "viur2import_blobsource",
    }


class Security(ConfigType):
    content_security_policy = {
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

    referrer_policy = "strict-origin"
    """Per default, we'll emit Referrer-Policy: strict-origin so no referrers leak to external services"""

    permissions_policy = {
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

    enable_coep = False
    """Shall we emit Cross-Origin-Embedder-Policy: require-corp?"""

    enable_coop = "same-origin"
    """Emit a Cross-Origin-Opener-Policy Header?
    Valid values are same-origin|same-origin-allow-popups|unsafe-none"""

    enable_corp = "same-origin"
    """Emit a Cross-Origin-Resource-Policy Header?
    Valid values are same-site|same-origin|cross-origin"""

    strict_transport_security = "max-age=22118400"
    """If set, ViUR will emit a HSTS HTTP-header with each request.
    Use security.enableStrictTransportSecurity to set this property"""

    x_frame_options = ("sameorigin", None)
    """If set, ViUR will emit an X-Frame-Options header,"""

    x_xss_protection = True
    """ViUR will emit an X-XSS-Protection header if set (the default),"""

    x_content_type_options = True
    """ViUR will emit X-Content-Type-Options: nosniff Header unless set to False"""

    x_permitted_cross_domain_policies = "none"
    """Unless set to logical none; ViUR will emit a X-Permitted-Cross-Domain-Policies with each request"""

    captcha_default_credentials = None
    """The default sitekey and secret to use for the captcha-bone.
    If set, must be a dictionary of "sitekey" and "secret".
    """

    password_recovery_key_length = 42
    """Length of the Password recovery key"""

    _mapping = {
        "contentSecurityPolicy": "content_security_policy",
        "referrerPolicy": "referrer_policy",
        "permissionsPolicy": "permissions_policy",
        "enableCOEP": "enable_coep",
        "enableCOOP": "enable_coop",
        "enableCORP": "enable_corp",
        "strictTransportSecurity": "strict_transport_security",
        "xFrameOptions": "x_frame_options",
        "xXssProtection": "x_xss_protection",
        "xContentTypeOptions": "x_content_type_options",
        "xPermittedCrossDomainPolicies": "x_permitted_cross_domain_policies",
        "captcha_defaultCredentials": "captcha_default_credentials",
        "captcha.defaultCredentials": "captcha_default_credentials",
    }


class Debug(ConfigType):
    trace = False
    """If enabled, trace any routing, HTTPExceptions and decorations for debugging and insight"""
    trace_exceptions = False
    """If enabled, user-generated exceptions from the viur.core.errors module won't be caught and handled"""
    trace_external_call_routing = False
    """If enabled, ViUR will log which (exposed) function are called from outside with what arguments"""
    trace_internal_call_routing = False
    """If enabled, ViUR will log which (internal-exposed) function are called from templates with what arguments"""
    skeleton_from_client = False
    """If enabled, log errors raises from skeleton.fromClient()"""

    dev_server_cloud_logging = False
    """If disabled the local logging will not send with requestLogger to the cloud"""

    disable_cache = False
    """If set to true, the decorator @enableCache from viur.core.cache has no effect"""

    _mapping = {
        "skeleton.fromClient": "skeleton_from_client",
        "traceExceptions": "trace_exceptions",
        "traceExternalCallRouting": "trace_external_call_routing",
        "traceInternalCallRouting": "trace_internal_call_routing",
        "skeleton_fromClient": "skeleton_from_client",
        "disableCache": "disable_cache",
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
        "viur.disable_cache": "debug.disable_cache",
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

print(os.getenv("VIUR_CORE_CONFIG_STRICT_MODE"))
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
