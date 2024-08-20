import datetime
import hashlib
import logging
import os
import typing as t
import warnings
from pathlib import Path

import google.auth

from viur.core.version import __version__

if t.TYPE_CHECKING:  # pragma: no cover
    from viur.core.email import EmailTransport
    from viur.core.skeleton import SkeletonInstance
    from viur.core.module import Module
    from viur.core.tasks import CustomEnvironmentHandler

# Construct an alias with a generic type to be able to write Multiple[str]
# TODO: Backward compatible implementation, refactor when viur-core
#       becomes >= Python 3.12 with a type statement (PEP 695)
_T = t.TypeVar("_T")
Multiple: t.TypeAlias = list[_T] | tuple[_T] | set[_T] | frozenset[_T]  # TODO: Refactor for Python 3.12


class CaptchaDefaultCredentialsType(t.TypedDict):
    """Expected type of global captcha credential, see :attr:`Security.captcha_default_credentials`"""
    sitekey: str
    secret: str


class ConfigType:
    """An abstract class for configurations.

    It ensures nesting and backward compatibility for the viur-core config
    """
    _mapping = {}
    """Mapping from old dict-key (must not be the entire key in case of nesting) to new attribute name"""

    _strict_mode = None
    """Internal strict mode for this instance.

     Use the property getter and setter to access it!"""

    _parent = None
    """Parent config instance"""

    def __init__(self, *,
                 strict_mode: bool = None,
                 parent: t.Union["ConfigType", None] = None):
        super().__init__()
        self._strict_mode = strict_mode
        self._parent = parent

    @property
    def _path(self):
        """Get the path in dot-Notation to the current config instance."""
        if self._parent is None:
            return ""
        return f"{self._parent._path}{self.__class__.__name__.lower()}."

    @property
    def strict_mode(self):
        """Determine if the config runs in strict mode.

        In strict mode, the dict-item-access backward compatibility is disabled,
        only attribute access is allowed.
        Alias mapping is also disabled. Only the real attribute  names are allowed.

        If self._strict_mode is None, it would inherit the value
        of the parent.
        If it's explicitly set to True or False, that value will be used.
        """
        if self._strict_mode is not None or self._parent is None:
            # This config has an explicit value set or there's no parent
            return self._strict_mode
        else:
            # no value set: inherit from the parent
            return self._parent.strict_mode

    @strict_mode.setter
    def strict_mode(self, value: bool | None) -> None:
        """Setter for the strict mode of the current instance.

        Does not affect other instances!
        """
        if not isinstance(value, (bool, type(None))):
            raise TypeError(f"Invalid {value=} for strict mode!")
        self._strict_mode = value

    def _resolve_mapping(self, key: str) -> str:
        """Resolve the mapping old dict -> new attribute.

        This method must not be called in strict mode!
        It can be overwritten to apply additional mapping.
        """
        if key in self._mapping:
            old, key = key, self._mapping[key]
            warnings.warn(
                f"Conf member {self._path}{old} is now {self._path}{key}!",
                DeprecationWarning,
                stacklevel=3,
            )
        return key

    def items(self,
              full_path: bool = False,
              recursive: bool = True,
              ) -> t.Iterator[tuple[str, t.Any]]:
        """Get all setting of this config as key-value mapping.

        :param full_path: Show prefix oder only the key.
        :param recursive: Call .items() on ConfigType members (children)?
        :return:
        """
        for key in dir(self):
            if key.startswith("_"):
                # skip internals, like _parent and _strict_mode
                continue
            value = getattr(self, key)
            if recursive and isinstance(value, ConfigType):
                yield from value.items(full_path, recursive)
            elif key not in dir(ConfigType):
                if full_path:
                    yield f"{self._path}{key}", value
                else:
                    yield key, value

    def get(self, key: str, default: t.Any = None) -> t.Any:
        """Return an item from the config, if it doesn't exist `default` is returned.

        :param key: The key for the attribute lookup.
        :param default: The fallback value.
        :return: The attribute value or the fallback value.
        """
        if self.strict_mode:
            raise SyntaxError(
                "In strict mode, the config must not be accessed "
                "with .get(). Only attribute access is allowed."
            )
        try:
            return getattr(self, key)
        except (KeyError, AttributeError):
            return default

    def __getitem__(self, key: str) -> t.Any:
        """Support the old dict-like syntax (getter).

        Not allowed in strict mode.
        """
        new_path = f"{self._path}{self._resolve_mapping(key)}"
        warnings.warn(f"conf uses now attributes! "
                      f"Use conf.{new_path} to access your option",
                      DeprecationWarning,
                      stacklevel=2)

        if self.strict_mode:
            raise SyntaxError(
                f"In strict mode, the config must not be accessed "
                f"with dict notation. "
                f"Only attribute access (conf.{new_path}) is allowed."
            )

        return getattr(self, key)

    def __getattr__(self, key: str) -> t.Any:
        """Resolve dot-notation and name mapping in not strict mode.

        This method is mostly executed by __getitem__, by the
        old dict-like access or by attr(conf, "key").
        In strict mode it does nothing except raising an AttributeError.
        """
        if self.strict_mode:
            raise AttributeError(
                f"AttributeError: '{self.__class__.__name__}' object has no"
                f" attribute '{key}' (strict mode is enabled)"
            )

        key = self._resolve_mapping(key)

        # Got an old dict-key and resolve the segment to the first dot (.) as attribute.
        if "." in key:
            first, remaining = key.split(".", 1)
            return getattr(getattr(self, first), remaining)

        return super().__getattribute__(key)

    def __setitem__(self, key: str, value: t.Any) -> None:
        """Support the old dict-like syntax (setter).

        Not allowed in strict mode.
        """
        new_path = f"{self._path}{self._resolve_mapping(key)}"
        if self.strict_mode:
            raise SyntaxError(
                f"In strict mode, the config must not be accessed "
                f"with dict notation. "
                f"Only attribute access (conf.{new_path}) is allowed."
            )

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
            first, remaining = key.split(".", 1)
            if not hasattr(self, first):
                # TODO: Compatibility, remove it in a future major release!
                #       This segment doesn't exist. Create it
                logging.warning(f"Creating new type for {first}")
                setattr(self, first, type(first.capitalize(), (ConfigType,), {})())
            getattr(self, first)[remaining] = value
            return

        return setattr(self, key, value)

    def __setattr__(self, key: str, value: t.Any) -> None:
        """Set attributes after applying the old -> new mapping

        In strict mode it does nothing except a super call
        for the default object behavior.
        """
        if self.strict_mode:
            return super().__setattr__(key, value)

        if not self.strict_mode:
            key = self._resolve_mapping(key)

        # Got an old dict-key and resolve the segment to the first dot (.) as attribute.
        if "." in key:
            # TODO: Shall we allow this in strict mode as well?
            first, remaining = key.split(".", 1)
            return setattr(getattr(self, first), remaining, value)

        return super().__setattr__(key, value)

    def __repr__(self) -> str:
        """Representation of this config"""
        return f"{self.__class__.__qualname__}({dict(self.items(False, False))})"


# Some values used more than once below
_project_id = google.auth.default()[1]
_app_version = os.getenv("GAE_VERSION")

# Determine our basePath (as os.getCWD is broken on appengine)
_project_base_path = Path().absolute()
_core_base_path = Path(__file__).parent.parent.parent  # fixme: this points to site-packages!!!


class Admin(ConfigType):
    """Administration tool configuration"""

    name: str = "ViUR"
    """Administration tool configuration"""

    logo: str = ""
    """URL for the Logo in the Topbar of the VI"""

    login_background: str = ""
    """URL for the big Image in the background of the VI Login screen"""

    login_logo: str = ""
    """URL for the Logo over the VI Login screen"""

    color_primary: str = "#d00f1c"
    """primary color for viur-admin"""

    color_secondary: str = "#333333"
    """secondary color for viur-admin"""

    module_groups: dict[str, dict[t.Literal["name", "icon", "sortindex"], str | int]] = {}
    """Module Groups for the admin tool

    Group modules in the sidebar in categories (groups).

    Example:
        conf.admin.module_groups = {
            "content": {
                "name": "Content",
                "icon": "file-text-fill",
                "sortindex": 10,
            },
            "shop": {
                "name": "Shop",
                "icon": "cart-fill",
                "sortindex": 20,
            },
        }

    To add a module to one of these groups (e.g. content), add `moduleGroup` to
    the admin_info of the module:
        "moduleGroup": "content",
    """

    _mapping: dict[str, str] = {
        "login.background": "login_background",
        "login.logo": "login_logo",
        "color.primary": "color_primary",
        "color.secondary": "color_secondary",
    }


class Security(ConfigType):
    """Security related settings"""

    force_ssl: bool = True
    """If true, all requests must be encrypted (ignored on development server)"""

    no_ssl_check_urls: Multiple[str] = ["/_tasks*", "/ah/*"]
    """List of URLs for which force_ssl is ignored.
    Add an asterisk to mark that entry as a prefix (exact match otherwise)"""

    content_security_policy: t.Optional[dict[str, dict[str, list[str]]]] = {
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

    referrer_policy: str = "strict-origin"
    """Per default, we'll emit Referrer-Policy: strict-origin so no referrers leak to external services

    See https://www.w3.org/TR/referrer-policy/
    """

    permissions_policy: dict[str, list[str]] = {
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

    enable_coep: bool = False
    """Shall we emit Cross-Origin-Embedder-Policy: require-corp?"""

    enable_coop: t.Literal[
        "unsafe-none", "same-origin-allow-popups",
        "same-origin", "same-origin-plus-COEP"] = "same-origin"
    """Emit a Cross-Origin-Opener-Policy Header?

    See https://html.spec.whatwg.org/multipage/browsers.html#cross-origin-opener-policy-value
    """

    enable_corp: t.Literal["same-origin", "same-site", "cross-origin"] = "same-origin"
    """Emit a Cross-Origin-Resource-Policy Header?

    See https://fetch.spec.whatwg.org/#cross-origin-resource-policy-header
    """

    strict_transport_security: t.Optional[str] = "max-age=22118400"
    """If set, ViUR will emit a HSTS HTTP-header with each request.
    Use security.enableStrictTransportSecurity to set this property"""

    x_frame_options: t.Optional[
        tuple[t.Literal["deny", "sameorigin", "allow-from"], t.Optional[str]]
    ] = ("sameorigin", None)
    """If set, ViUR will emit an X-Frame-Options header

    In case of allow-from, the second parameters must be the host-url.
    Otherwise, it can be None.
    """

    x_xss_protection: t.Optional[bool] = True
    """ViUR will emit an X-XSS-Protection header if set (the default)"""

    x_content_type_options: bool = True
    """ViUR will emit X-Content-Type-Options: nosniff Header unless set to False"""

    x_permitted_cross_domain_policies: t.Optional[t.Literal["none", "master-only", "by-content-type", "all"]] = "none"
    """Unless set to logical none; ViUR will emit a X-Permitted-Cross-Domain-Policies with each request"""

    captcha_default_credentials: t.Optional[CaptchaDefaultCredentialsType] = None
    """The default sitekey and secret to use for the :class:`CaptchaBone`.
    If set, must be a dictionary of "sitekey" and "secret".
    """

    captcha_enforce_always: bool = False
    """By default a captcha of the :class:`CaptchaBone` must not be solved on a local development server
    or by a root user. But for development it can be helpful to test the implementation
    on a local development server. Setting this flag to True, disables this behavior and
    enforces always a valid captcha.
    """

    password_recovery_key_length: int = 42
    """Length of the Password recovery key"""

    closed_system: bool = False
    """If `True` it activates a mode in which only authenticated users can access all routes."""

    admin_allowed_paths: t.Iterable[str] = [
        "vi",
        "vi/skey",
        "vi/settings",
        "vi/user/auth_*",
        "vi/user/f2_*",
        "vi/user/getAuthMethods",  # FIXME: deprecated, use `login` for this
        "vi/user/login",
    ]
    """Specifies admin tool paths which are being accessible without authenticated user."""

    closed_system_allowed_paths: t.Iterable[str] = admin_allowed_paths + [
        "",  # index site
        "json/skey",
        "json/user/auth_*",
        "json/user/f2_*",
        "json/user/getAuthMethods",  # FIXME: deprecated, use `login` for this
        "json/user/login",
        "user/auth_*",
        "user/f2_*",
        "user/getAuthMethods",  # FIXME: deprecated, use `login` for this
        "user/login",
    ]
    """Paths that are accessible without authentication in a closed system, see `closed_system` for details."""

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
    """Several debug flags"""

    trace: bool = False
    """If enabled, trace any routing, HTTPExceptions and decorations for debugging and insight"""

    trace_exceptions: bool = False
    """If enabled, user-generated exceptions from the viur.core.errors module won't be caught and handled"""

    trace_external_call_routing: bool = False
    """If enabled, ViUR will log which (exposed) function are called from outside with what arguments"""

    trace_internal_call_routing: bool = False
    """If enabled, ViUR will log which (internal-exposed) function are called from templates with what arguments"""

    skeleton_from_client: bool = False
    """If enabled, log errors raises from skeleton.fromClient()"""

    dev_server_cloud_logging: bool = False
    """If disabled the local logging will not send with requestLogger to the cloud"""

    disable_cache: bool = False
    """If set to true, the decorator @enableCache from viur.core.cache has no effect"""

    _mapping = {
        "skeleton.fromClient": "skeleton_from_client",
        "traceExceptions": "trace_exceptions",
        "traceExternalCallRouting": "trace_external_call_routing",
        "traceInternalCallRouting": "trace_internal_call_routing",
        "skeleton_fromClient": "skeleton_from_client",
        "disableCache": "disable_cache",
    }


class Email(ConfigType):
    """Email related settings."""

    log_retention: datetime.timedelta = datetime.timedelta(days=30)
    """For how long we'll keep successfully send emails in the viur-emails table"""

    transport_class: t.Type["EmailTransport"] = None
    """Class that actually delivers the email using the service provider
    of choice. See email.py for more details
    """

    mailjet_api_key: t.Optional[str] = None
    """API Key for MailJet"""

    mailjet_api_secret: t.Optional[str] = None
    """API Secret for MailJet"""

    sendinblue_api_key: t.Optional[str] = None
    """API Key for SendInBlue (now Brevo) for the EmailTransportSendInBlue
    """

    sendinblue_thresholds: tuple[int] | list[int] = (1000, 500, 100)
    """Warning thresholds for remaining email quota

    Used by email.EmailTransportSendInBlue.check_sib_quota
    """

    send_from_local_development_server: bool = False
    """If set, we'll enable sending emails from the local development server.
    Otherwise, they'll just be logged.
    """

    recipient_override: str | list[str] | t.Callable[[], str | list[str]] | t.Literal[False] = None
    """If set, all outgoing emails will be sent to this address
    (overriding the 'dests'-parameter in email.sendEmail)
    """

    sender_override: str | None = None
    """If set, this sender will be used, regardless of what the templates advertise as sender"""

    admin_recipients: str | list[str] | t.Callable[[], str | list[str]] = None
    """Sets recipients for mails send with email.sendEMailToAdmins. If not set, all root users will be used."""

    _mapping = {
        "logRetention": "log_retention",
        "transportClass": "transport_class",
        "sendFromLocalDevelopmentServer": "send_from_local_development_server",
        "recipientOverride": "recipient_override",
        "senderOverride": "sender_override",
        "admin_recipients": "admin_recipients",
        "sendInBlue.apiKey": "sendinblue_api_key",
        "sendInBlue.thresholds": "sendinblue_thresholds",
    }


class I18N(ConfigType):
    """All i18n, multilang related settings."""

    available_languages: Multiple[str] = ["en"]
    """List of language-codes, which are valid for this application"""

    default_language: str = "en"
    """Unless overridden by the Project: Use english as default language"""

    domain_language_mapping: dict[str, str] = {}
    """Maps Domains to alternative default languages"""

    language_alias_map: dict[str, str] = {}
    """Allows mapping of certain languages to one translation (i.e. us->en)"""

    language_method: t.Literal["session", "url", "domain"] = "session"
    """Defines how translations are applied:
        - session: Per Session
        - url: inject language prefix in url
        - domain: one domain per language
    """

    language_module_map: dict[str, dict[str, str]] = {}
    """Maps modules to their translation (if set)"""

    @property
    def available_dialects(self) -> list[str]:
        """Main languages and language aliases"""
        # Use a dict to keep the order and remove duplicates
        res = dict.fromkeys(self.available_languages)
        res |= self.language_alias_map
        return list(res.keys())

    add_missing_translations: bool = False
    """Add missing translation into datastore.

    If a key is not found in the translation table when a translation is
    rendered, a database entry is created with the key and hint and
    default value (if set) so that the translations
    can be entered in the administration.
    """


class User(ConfigType):
    """User, session, login related settings"""

    access_rights: Multiple[str] = ["root", "admin"]
    """Additional access rights available on this project"""

    roles: dict[str, str] = {
        "custom": "Custom",
        "user": "User",
        "viewer": "Viewer",
        "editor": "Editor",
        "admin": "Administrator",
    }
    """User roles available on this project"""

    session_life_time: int = 60 * 60
    """Default is 60 minutes lifetime for ViUR sessions"""

    session_persistent_fields_on_login: Multiple[str] = ["language"]
    """If set, these Fields will survive the session.reset() called on user/login"""

    session_persistent_fields_on_logout: Multiple[str] = ["language"]
    """If set, these Fields will survive the session.reset() called on user/logout"""

    max_password_length: int = 512
    """Prevent Denial of Service attacks using large inputs for pbkdf2"""

    otp_issuer: t.Optional[str] = None
    """The name of the issuer for the opt token"""

    google_client_id: t.Optional[str] = None
    """OAuth Client ID for Google Login"""

    google_gsuite_domains: list[str] = []
    """A list of domains. When a user signs in for the first time with a
    Google account using Google OAuth sign-in, and the user's email address
    belongs to one of the listed domains, a user account (UserSkel) is created.
    If the user's email address belongs to any other domain,
    no account is created."""


class Instance(ConfigType):
    """All app instance related settings information"""
    app_version: str = _app_version
    """Name of this version as deployed to the appengine"""

    core_base_path: Path = _core_base_path
    """The base path of the core, can be used to find file in the core folder"""

    is_dev_server: bool = os.getenv("GAE_ENV") == "localdev"
    """Determine whether instance is running on a local development server"""

    project_base_path: Path = _project_base_path
    """The base path of the project, can be used to find file in the project folder"""

    project_id: str = _project_id
    """The instance's project ID"""

    version_hash: str = hashlib.sha256(f"{_app_version}{project_id}".encode("UTF-8")).hexdigest()[:10]
    """Version hash that does not reveal the actual version name, can be used for cache-busting static resources"""


class Conf(ConfigType):
    """Conf class wraps the conf dict and allows to handle
    deprecated keys or other special operations.
    """

    bone_boolean_str2true: Multiple[str | int] = ("true", "yes", "1")
    """Allowed values that define a str to evaluate to true"""

    cache_environment_key: t.Optional[t.Callable[[], str]] = None
    """If set, this function will be called for each cache-attempt
    and the result will be included in the computed cache-key"""

    # FIXME VIUR4: REMOVE ALL COMPATIBILITY MODES!
    compatibility: Multiple[str] = [
        "json.bone.structure.camelcasenames",  # use camelCase attribute names (see #637 for details)
        "json.bone.structure.keytuples",  # use classic structure notation: `"structure = [["key", {...}] ...]` (#649)
        "json.bone.structure.inlists",  # dump skeleton structure with every JSON list response (#774 for details)
        "bone.select.structure.values.keytuple",  # render old-style tuple-list in SelectBone's values structure (#1203)
    ]
    """Backward compatibility flags; Remove to enforce new style."""

    db_engine: str = "viur.datastore"
    """Database engine module"""

    error_handler: t.Callable[[Exception], str] | None = None
    """If set, ViUR calls this function instead of rendering the viur.errorTemplate if an exception occurs"""

    error_logo: str = None
    """Path to a logo (static file). Will be used for the default error template"""

    static_embed_svg_path: str = "/static/svgs/"
    """Path to the static SVGs folder. Will be used by the jinja-renderer-method: embedSvg"""

    file_hmac_key: str = None
    """Hmac-Key used to sign download urls - set automatically"""

    # TODO: separate this type hints and use it in the File module as well
    file_derivations: dict[str, t.Callable[["SkeletonInstance", dict, dict], list[tuple[str, float, str, t.Any]]]] = {}
    """Call-Map for file pre-processors"""

    file_thumbnailer_url: t.Optional[str] = None
    # TODO: """docstring"""

    main_app: "Module" = None
    """Reference to our pre-build Application-Instance"""

    main_resolver: dict[str, dict] = None
    """Dictionary for Resolving functions for URLs"""

    max_post_params_count: int = 250
    """Upper limit of the amount of parameters we accept per request. Prevents Hash-Collision-Attacks"""

    param_filter_function: t.Callable[[str, str], bool] = lambda _, key, value: key.startswith("_")
    """
    Function which decides if a request parameter should be used or filtered out.
    Returning True means to filter out.
    """

    moduleconf_admin_info: dict[str, t.Any] = {
        "icon": "gear-fill",
        "display": "hidden",
    }
    """Describing the internal ModuleConfig-module"""

    script_admin_info: dict[str, t.Any] = {
        "icon": "file-code-fill",
        "display": "hidden",
    }
    """Describing the Script module"""

    render_html_download_url_expiration: t.Optional[float | int] = None
    """The default duration, for which downloadURLs generated by the html renderer will stay valid"""

    render_json_download_url_expiration: t.Optional[float | int] = None
    """The default duration, for which downloadURLs generated by the json renderer will stay valid"""

    request_preprocessor: t.Optional[t.Callable[[str], str]] = None
    """Allows the application to register a function that's called before the request gets routed"""

    search_valid_chars: str = "abcdefghijklmnopqrstuvwxyzäöüß0123456789"
    """Characters valid for the internal search functionality (all other chars are ignored)"""

    skeleton_search_path: Multiple[str] = [
        "/skeletons/",  # skeletons of the project
        "/viur/core/",  # system-defined skeletons of viur-core
        "/viur-core/core/"  # system-defined skeletons of viur-core, only used by editable installation
    ]
    """Priority, in which skeletons are loaded"""

    _tasks_custom_environment_handler: t.Optional["CustomEnvironmentHandler"] = None

    @property
    def tasks_custom_environment_handler(self) -> t.Optional["CustomEnvironmentHandler"]:
        """
        Preserve additional environment in deferred tasks.

        If set, it must be an instance of CustomEnvironmentHandler
        for serializing/restoring environment data.
        """
        return self._tasks_custom_environment_handler

    @tasks_custom_environment_handler.setter
    def tasks_custom_environment_handler(self, value: "CustomEnvironmentHandler") -> None:
        from .tasks import CustomEnvironmentHandler
        if isinstance(value, CustomEnvironmentHandler) or value is None:
            self._tasks_custom_environment_handler = value
        elif isinstance(value, tuple):
            if len(value) != 2:
                raise ValueError(f"Expected a (serialize_env_func, restore_env_func) pair")
            warnings.warn(
                f"tuple is deprecated, please provide a CustomEnvironmentHandler object!",
                DeprecationWarning, stacklevel=2,
            )
            # Construct an CustomEnvironmentHandler class on the fly to be backward compatible
            cls = type("ProjectCustomEnvironmentHandler", (CustomEnvironmentHandler,),
                       # serialize and restore will be bound methods.
                       # Therefore, consume the self argument with lambda.
                       {"serialize": lambda self: value[0](),
                        "restore": lambda self, obj: value[1](obj)})
            self._tasks_custom_environment_handler = cls()
        else:
            raise ValueError(f"Invalid type {type(value)}. Expected a CustomEnvironmentHandler object.")

    valid_application_ids: list[str] = []
    """Which application-ids we're supposed to run on"""

    version: tuple[int, int, int] = tuple(int(part) if part.isdigit() else part for part in __version__.split(".", 3))
    """Semantic version number of viur-core as a tuple of 3 (major, minor, patch-level)"""

    viur2import_blobsource: t.Optional[dict[t.Literal["infoURL", "gsdir"], str]] = None
    """Configuration to import file blobs from ViUR2"""

    def __init__(self, strict_mode: bool = False):
        super().__init__()
        self._strict_mode = strict_mode
        self.admin = Admin(parent=self)
        self.security = Security(parent=self)
        self.debug = Debug(parent=self)
        self.email = Email(parent=self)
        self.i18n = I18N(parent=self)
        self.user = User(parent=self)
        self.instance = Instance(parent=self)

    _mapping = {
        # debug
        "viur.dev_server_cloud_logging": "debug.dev_server_cloud_logging",
        "viur.disable_cache": "debug.disable_cache",
        # i18n
        "viur.availableLanguages": "i18n.available_languages",
        "viur.defaultLanguage": "i18n.default_language",
        "viur.domainLanguageMapping": "i18n.domain_language_mapping",
        "viur.languageAliasMap": "i18n.language_alias_map",
        "viur.languageMethod": "i18n.language_method",
        "viur.languageModuleMap": "i18n.language_module_map",
        # user
        "viur.accessRights": "user.access_rights",
        "viur.maxPasswordLength": "user.max_password_length",
        "viur.otp.issuer": "user.otp_issuer",
        "viur.session.lifeTime": "user.session_life_time",
        "viur.session.persistentFieldsOnLogin": "user.session_persistent_fields_on_login",
        "viur.session.persistentFieldsOnLogout": "user.session_persistent_fields_on_logout",
        "viur.user.roles": "user.roles",
        "viur.user.google.clientID": "user.google_client_id",
        "viur.user.google.gsuiteDomains": "user.google_gsuite_domains",
        # instance
        "viur.instance.app_version": "instance.app_version",
        "viur.instance.core_base_path": "instance.core_base_path",
        "viur.instance.is_dev_server": "instance.is_dev_server",
        "viur.instance.project_base_path": "instance.project_base_path",
        "viur.instance.project_id": "instance.project_id",
        "viur.instance.version_hash": "instance.version_hash",
        # security
        "viur.forceSSL": "security.force_ssl",
        "viur.noSSLCheckUrls": "security.no_ssl_check_urls",
        # old viur-prefix
        "viur.cacheEnvironmentKey": "cache_environment_key",
        "viur.contentSecurityPolicy": "content_security_policy",
        "viur.bone.boolean.str2true": "bone_boolean_str2true",
        "viur.db.engine": "db_engine",
        "viur.errorHandler": "error_handler",
        "viur.static.embedSvg.path": "static_embed_svg_path",
        "viur.file.hmacKey": "file_hmac_key",
        "viur.file_hmacKey": "file_hmac_key",
        "viur.file.derivers": "file_derivations",
        "viur.file.thumbnailerURL": "file_thumbnailer_url",
        "viur.mainApp": "main_app",
        "viur.mainResolver": "main_resolver",
        "viur.maxPostParamsCount": "max_post_params_count",
        "viur.moduleconf.admin_info": "moduleconf_admin_info",
        "viur.script.admin_info": "script_admin_info",
        "viur.render.html.downloadUrlExpiration": "render_html_download_url_expiration",
        "viur.downloadUrlFor.expiration": "render_html_download_url_expiration",
        "viur.render.json.downloadUrlExpiration": "render_json_download_url_expiration",
        "viur.requestPreprocessor": "request_preprocessor",
        "viur.searchValidChars": "search_valid_chars",
        "viur.skeleton.searchPath": "skeleton_search_path",
        "viur.tasks.customEnvironmentHandler": "tasks_custom_environment_handler",
        "viur.validApplicationIDs": "valid_application_ids",
        "viur.viur2import.blobsource": "viur2import_blobsource",
    }

    def _resolve_mapping(self, key: str) -> str:
        """Additional mapping for new sub confs."""
        if key.startswith("viur.") and key not in self._mapping:
            key = key.removeprefix("viur.")
        return super()._resolve_mapping(key)


conf = Conf(
    strict_mode=os.getenv("VIUR_CORE_CONFIG_STRICT_MODE", "").lower() == "true",
)
