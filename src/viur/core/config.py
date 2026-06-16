import datetime
import hashlib
import logging
import os
import re
import typing as t
import warnings
from pathlib import Path

import google.auth
from google.appengine.api.memcache import Client

from viur.core.version import __version__
from viur.core.current import user as current_user

if t.TYPE_CHECKING:  # pragma: no cover
    from viur.core.bones.text import HtmlBoneConfiguration
    from viur.core.email import EmailTransport
    from viur.core.skeleton import SkeletonInstance
    from viur.core.module import Module
    from viur.core.tasks import CustomEnvironmentHandler
    from viur.core import i18n

# Construct an alias with a generic type to be able to write Multiple[str]
# TODO: Backward compatible implementation, refactor when viur-core
#       becomes >= Python 3.12 with a type statement (PEP 695)
_T = t.TypeVar("_T")
Multiple: t.TypeAlias = list[_T] | tuple[_T] | set[_T] | frozenset[_T]  # TODO: Refactor for Python 3.12




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


class Database(ConfigType):
    query_external_limit: int = 100
    """Sets the maximum query limit allowed by external filters."""

    query_default_limit: int = 30
    """Sets the default query limit for all queries."""

    memcache_client: Client | None = None
    """If set, ViUR cache data for the db.get in the Memcache for faster access."""

    create_access_log: bool = True
    """If False no access log will be created. But then the caching is disabled too."""


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
    """If set, viur will emit a CSP http-header with each request.
    Use :meth:`viur.core.config.Security.add_csp_rule` to set this property."""

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
    :meth:`viur.core.config.Security.set_permission_policy_directive` to include at least "self"
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

    captcha_default_public_key: t.Optional[str] = None
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
        "vi/config",
        "vi/skey",
        "vi/user/auth_*",
        "vi/user/f2_*",
        "vi/user/login",
        "vi/user/select_authentication_provider",
        # DEPRECATED:
        "vi/settings",  # FIXME: Deprecated; vi-admin 4.x backward compatiblity
        "vi/user/getAuthMethods",  # FIXME: Deprecated; vi-admin 4.x backward compatiblity
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
        "user/select_authentication_provider",
        "user/login",
    ]
    """Paths that are accessible without authentication in a closed system, see `closed_system` for details."""

    # CORS Settings

    cors_origins: t.Iterable[str | re.Pattern] | t.Literal["*"] = []
    """Allowed origins
    Access-Control-Allow-Origin

    Pattern should be case-insensitive, for example:
        >>> re.compile(r"^http://localhost:(\d{4,5})/?$", flags=re.IGNORECASE)
    """  # noqa

    cors_origins_use_wildcard: bool = False
    """Use * for Access-Control-Allow-Origin -- if possible"""

    cors_methods: t.Iterable[str] = ["get", "head", "post", "options"]  # , "put", "patch", "delete"]
    """Access-Control-Request-Method"""

    cors_allow_headers: t.Iterable[str | re.Pattern] | t.Literal["*"] = []
    """Access-Control-Request-Headers

    Can also be set for specific @exposed methods with the @cors decorator.

    Pattern should be case-insensitive, for example:
        >>> re.compile(r"^X-ViUR-.*$", flags=re.IGNORECASE)
    """

    cors_allow_credentials: bool = False
    """
    Set Access-Control-Allow-Credentials to true
    to support fetch requests with credentials: include
    """

    cors_max_age: datetime.timedelta | None = None
    """Allow caching"""

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
    }

    VALID_REFERRER_POLICIES = [
        "no-referrer",
        "no-referrer-when-downgrade",
        "origin",
        "origin-when-cross-origin",
        "same-origin",
        "strict-origin",
        "strict-origin-when-cross-origin",
        "unsafe-url",
    ]
    """Valid values for the Referrer-Policy header (https://www.w3.org/TR/referrer-policy/)."""

    def enable_strict_transport_security(
        self,
        max_age: int = 365 * 24 * 60 * 60,
        include_sub_domains: bool = False,
        preload: bool = False,
    ) -> None:
        """Enable HTTP Strict Transport Security (HSTS)."""
        self.strict_transport_security = f"max-age={max_age}"
        if include_sub_domains:
            self.strict_transport_security += "; includeSubDomains"
        if preload:
            self.strict_transport_security += "; preload"

    def set_x_frame_options(self, action: str, uri: t.Optional[str] = None) -> None:
        """Set X-Frame-Options to prevent click-jacking. ``action``: off | deny | sameorigin | allow-from."""
        if action == "off":
            self.x_frame_options = None
        elif action in ("deny", "sameorigin"):
            self.x_frame_options = (action, None)
        elif action == "allow-from":
            if uri is None or not (uri.lower().startswith("https://") or uri.lower().startswith("http://")):
                raise ValueError("If action is allow-from, an uri MUST be given and start with http(s)://")
            self.x_frame_options = (action, uri)

    def set_x_xss_protection(self, enable: t.Optional[bool]) -> None:
        """Set the X-XSS-Protection header. ``enable``: True | False | None (drop the header)."""
        if enable is True or enable is False or enable is None:
            self.x_xss_protection = enable
        else:
            raise ValueError("enable must be exactly one of None | True | False")

    def set_x_content_type_no_sniff(self, enable: bool) -> None:
        """Emit ``X-Content-Type-Options: nosniff`` when ``enable`` is True."""
        if enable is True or enable is False:
            self.x_content_type_options = enable
        else:
            raise ValueError("enable must be one of True | False")

    def set_x_permitted_cross_domain_policies(self, value: t.Optional[str]) -> None:
        """Set the X-Permitted-Cross-Domain-Policies header (or disable it with None)."""
        if value not in (None, "none", "master-only", "by-content-type", "all"):
            raise ValueError('value must be one of [None, "none", "master-only", "by-content-type", "all"]')
        self.x_permitted_cross_domain_policies = value

    def set_referrer_policy(self, policy: str) -> None:
        """Set the Referrer-Policy header (must be one of :attr:`VALID_REFERRER_POLICIES`)."""
        assert policy in self.VALID_REFERRER_POLICIES, f"Policy must be one of {self.VALID_REFERRER_POLICIES}"
        self.referrer_policy = policy

    def set_permission_policy_directive(self, directive: str, allow_list: t.Optional[list[str]]) -> None:
        """Set a single Permissions-Policy directive. Empty list disables the feature."""
        self.permissions_policy[directive] = allow_list

    def set_cross_origin_isolation(self, coep: bool, coop: str, corp: str) -> None:
        """Configure COEP/COOP/CORP cross-origin isolation headers (see https://web.dev/coop-coep)."""
        assert coop in ("same-origin", "same-origin-allow-popups", "unsafe-none"), "Invalid value for the COOP Header"
        assert corp in ("same-site", "same-origin", "cross-origin"), "Invalid value for the CORP Header"
        self.enable_coep = bool(coep)
        self.enable_coop = coop
        self.enable_corp = corp

    _csp_header_cache: dict[str, str] = {}
    """Derived cache of built CSP header strings; populated by :meth:`finalize`. Internal."""

    def add_csp_rule(self, object_type: str, src_or_directive: str, enforce_mode: str = "monitor") -> None:
        """Add a Content-Security-Policy rule. Call before the app is built (i.e. before ``setup()``).

        :param object_type: directive type, e.g. ``script-src``, ``img-src``, ``report-uri``, ...
        :param src_or_directive: an allowed source/host or a CSP keyword like ``self``, ``unsafe-inline``.
        :param enforce_mode: ``enforce`` or ``monitor`` (report-only).
        """
        assert enforce_mode in ("monitor", "enforce"), "enforce_mode must be 'monitor' or 'enforce'!"
        assert object_type in {
            "default-src", "script-src", "object-src", "style-src", "img-src", "media-src",
            "frame-src", "font-src", "connect-src", "report-uri", "frame-ancestors", "child-src",
            "form-action", "require-trusted-types-for",
        }, f"object_type {object_type!r} is not a valid CSP directive"
        assert conf.main_app is None, "You cannot modify CSP rules after the app has been built!"
        assert not any(c in src_or_directive for c in (";", "'", '"', "\n", ",")), \
            "Invalid character in src_or_directive!"
        if self.content_security_policy is None:
            self.content_security_policy = {}
        if enforce_mode not in self.content_security_policy:
            self.content_security_policy[enforce_mode] = {}
        if object_type == "report-uri":
            self.content_security_policy[enforce_mode]["report-uri"] = [src_or_directive]
        else:
            if object_type not in self.content_security_policy[enforce_mode]:
                self.content_security_policy[enforce_mode][object_type] = []
            if src_or_directive not in self.content_security_policy[enforce_mode][object_type]:
                self.content_security_policy[enforce_mode][object_type].append(src_or_directive)

    def _build_csp_header_cache(self) -> None:
        """(Re)build :attr:`_csp_header_cache` from :attr:`content_security_policy`.

        NOTE: project-wide CSP does NOT quote ``nonce-`` values (a nonce must not be reused across
        requests); per-request :meth:`extend_csp` does quote them. Keep these rules distinct.
        """
        self._csp_header_cache = {}
        if not self.content_security_policy:
            return
        for enforce_mode in ("monitor", "enforce"):
            if enforce_mode not in self.content_security_policy:
                continue
            res = ""
            for key, values in self.content_security_policy[enforce_mode].items():
                res += key
                for value in values:
                    res += " "
                    if value in {"self", "unsafe-inline", "unsafe-eval", "script", "none"} \
                            or any(value.startswith(p) for p in ("sha256-", "sha384-", "sha512-")):
                        res += f"'{value}'"
                    else:
                        res += value
                res += "; "
            header = "Content-Security-Policy-Report-Only" if enforce_mode == "monitor" else "Content-Security-Policy"
            self._csp_header_cache[header] = res

    _permissions_policy_header: str = ""
    """Derived cache of the built Permissions-Policy header string; populated by :meth:`finalize`. Internal."""

    def _build_permissions_policy_header(self) -> None:
        """(Re)build :attr:`_permissions_policy_header` from :attr:`permissions_policy`."""
        self._permissions_policy_header = ", ".join(
            "%s=(%s)" % (k, " ".join(('"%s"' % x if x != "self" else x) for x in v))
            for k, v in self.permissions_policy.items()
        )

    def extend_csp(self, additional_rules: t.Optional[dict] = None, override_rules: t.Optional[dict] = None) -> None:
        """Extend/override the project-wide CSP for the *current* request only (``enforce`` mode).

        ``additional_rules`` values are appended, ``override_rules`` values replace (None removes a key).
        Unlike the project-wide config, per-request rules MAY contain ``nonce-`` values.
        """
        from viur.core import current
        assert additional_rules or override_rules, "Either additional_rules or override_rules must be given!"
        tmp: dict = {}
        if self.content_security_policy and self.content_security_policy.get("enforce"):
            tmp.update({k: v[:] for k, v in self.content_security_policy["enforce"].items()})
        if override_rules:
            for k, v in override_rules.items():
                if v is None and k in tmp:
                    del tmp[k]
                else:
                    tmp[k] = v
        if additional_rules:
            for k, v in additional_rules.items():
                if k not in tmp:
                    tmp[k] = []
                tmp[k].extend(v)
        res = ""
        for key, values in tmp.items():
            res += key
            for value in values:
                res += " "
                if value in {"self", "unsafe-inline", "unsafe-eval", "script", "none"} \
                        or any(value.startswith(p) for p in ("nonce-", "sha256-", "sha384-", "sha512-")):
                    res += f"'{value}'"
                else:
                    res += value
            res += "; "
        current.request.get().response.headers["Content-Security-Policy"] = res

    def finalize(self) -> None:
        """Build the derived header caches and validate the security config. Called once by ``core.setup()``."""
        self._build_csp_header_cache()
        self._build_permissions_policy_header()

        for header_name in self._csp_header_cache:
            if not header_name.startswith("Content-Security-Policy"):
                raise AssertionError("Got unexpected header in Security._csp_header_cache")
        if self.strict_transport_security:
            if not self.strict_transport_security.startswith("max-age"):
                raise AssertionError("Got unexpected value in Security.strict_transport_security")
        cross_domain_policies = {None, "none", "master-only", "by-content-type", "all"}
        if self.x_permitted_cross_domain_policies not in cross_domain_policies:
            raise AssertionError(
                f"Security.x_permitted_cross_domain_policies must be one of {cross_domain_policies!r}")
        if self.x_frame_options is not None and isinstance(self.x_frame_options, tuple):
            mode, uri = self.x_frame_options
            assert mode in ("deny", "sameorigin", "allow-from")
            if mode == "allow-from":
                assert uri is not None and (uri.lower().startswith("https://") or uri.lower().startswith("http://"))

    def update_response_headers(self, response, *, is_ssl: bool) -> None:
        """Emit all configured security headers onto ``response`` (a webob Response).

        Must be called BEFORE the request handler runs, so handlers/:meth:`extend_csp` can override CSP.
        """
        if self._csp_header_cache:
            for header_name, value in self._csp_header_cache.items():
                response.headers[header_name] = value
        if is_ssl and self.strict_transport_security:
            response.headers["Strict-Transport-Security"] = self.strict_transport_security
        if self.x_content_type_options:
            response.headers["X-Content-Type-Options"] = "nosniff"
        if self.x_xss_protection is not None:
            if self.x_xss_protection:
                response.headers["X-XSS-Protection"] = "1; mode=block"
            elif self.x_xss_protection is False:
                response.headers["X-XSS-Protection"] = "0"
        if self.x_frame_options is not None and isinstance(self.x_frame_options, tuple):
            mode, uri = self.x_frame_options
            if mode in ("deny", "sameorigin"):
                response.headers["X-Frame-Options"] = mode
            elif mode == "allow-from":
                response.headers["X-Frame-Options"] = f"allow-from {uri}"
        if self.x_permitted_cross_domain_policies is not None:
            response.headers["X-Permitted-Cross-Domain-Policies"] = self.x_permitted_cross_domain_policies
        if self.referrer_policy:
            response.headers["Referrer-Policy"] = self.referrer_policy
        if self._permissions_policy_header:
            response.headers["Permissions-Policy"] = self._permissions_policy_header
        if self.enable_coep:
            response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        if self.enable_coop:
            response.headers["Cross-Origin-Opener-Policy"] = self.enable_coop
        if self.enable_corp:
            response.headers["Cross-Origin-Resource-Policy"] = self.enable_corp


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

    trace_queries: bool = False
    """If enabled, ViUR will log each query that run"""

    skeleton_from_client: bool = False
    """If enabled, log errors raises from skeleton.fromClient()"""

    dev_server_cloud_logging: bool = False
    """If disabled the local logging will not send with requestLogger to the cloud"""

    disable_cache: bool = False
    """If set to true, the decorator @enableCache from viur.core.cache has no effect"""

    trace_headers: bool = False
    """If enabled, log the incoming request headers and the final outgoing response headers per request.
    Sensitive headers are redacted (see :attr:`trace_headers_redact`)."""

    trace_headers_redact: Multiple[str] = ("Authorization", "Proxy-Authorization", "Cookie", "Set-Cookie")
    """Header names (matched case-insensitively) whose values are redacted in :attr:`trace_headers` output.
    An empty collection disables redaction (full raw dump)."""

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

    transport_class: "EmailTransport" = None
    """EmailTransport instance that actually delivers the email using the service provider
    of choice. See :module:`core.email` for more details
    """

    send_from_local_development_server: bool = False
    """If set, we'll enable sending emails from the local development server.
    Otherwise, they'll just be logged.
    """

    recipient_override: str | list[str] | t.Callable[[], str | list[str]] | t.Literal[False] = None
    """If set, all outgoing emails will be sent to this address
    (overriding the 'dests'-parameter in :meth:`core.email.send_email`)
    """

    sender_default: str = f"viur@{_project_id}.appspotmail.com"
    """This sender is used by default for emails.
    It can be overridden for a specific email by passing the `sender` argument
    to :meth:`core.email.send_email` or for all emails with :attr:`sender_override`.
    """

    sender_override: str | None = None
    """If set, this sender will be used, regardless of what the templates advertise as sender"""

    admin_recipients: str | list[str] | t.Callable[[], str | list[str]] = None
    """Sets recipients for mails send with :meth:`core.email.send_email_to_admins`.
    If not set, all root users will be used."""

    _mapping = {
        "logRetention": "log_retention",
        "transportClass": "transport_class",
        "sendFromLocalDevelopmentServer": "send_from_local_development_server",
        "recipientOverride": "recipient_override",
        "senderOverride": "sender_override",
        "sendInBlue.apiKey": "sendinblue_api_key",
        "sendInBlue.thresholds": "sendinblue_thresholds",
    }


class History(ConfigType):
    databases: Multiple[str] = ["viur"]
    """All history related settings."""
    excluded_actions: Multiple[str] = []
    """List of all action that are should not be logged."""
    excluded_kinds: Multiple[str] = []
    """List of all kinds that should be logged."""


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

    language_method: t.Literal["session", "url", "domain", "header"] = "session"
    """Defines how translations are applied:
        - session: Per Session
        - url: inject language prefix in url
        - domain: one domain per language
        - header: Per Http-Header
    """

    language_module_map: dict[str, dict[str, str]] = {}
    """Maps modules to their translation (if set)"""

    auto_translate_bones: bool = True
    """Defines whether bone descr and categories should be automatically translated via i18n.translate-objects."""

    @property
    def available_dialects(self) -> list[str]:
        """Main languages and language aliases"""
        # Use a dict to keep the order and remove duplicates
        res = dict.fromkeys(self.available_languages)
        res |= self.language_alias_map
        return list(res.keys())

    add_missing_translations: (bool | str | t.Iterable[str] | "i18n.AddMissing"
                               | t.Callable[["i18n.translate"], t.Union[bool, "i18n.AddMissing"]]) = False
    """Add missing translation into datastore, optionally with given fnmatch-patterns.

    If a key is not found in the translation table when a translation is
    rendered, a database entry is created with the key and hint and
    default value (if set) so that the translations
    can be entered in the administration.

    Instead of setting add_missing_translations to a boolean, it can also be set to
    a pattern or iterable of fnmatch-patterns; Only translation keys matching these
    patterns will be automatically added.
    If a callable is provided, it will be called with the translation object to make a complex decision.
    """

    def _dump_can_view(self, _key):
        return bool(current_user.get())

    dump_can_view: t.Callable[[t.Self, str], bool] = _dump_can_view
    """Customizable callback for translation.dump() to verify if a specific translation key can be queried.

    This logic is omitted for translations flagged public."""


class User(ConfigType):
    """User, session, login related settings"""

    access_rights: Multiple[str] = [
        "root",
        "admin",
        "scriptor",
    ]
    """Additional access flags available for users on this project.

    There are three default flags:
    - `root` is allowed to view/add/edit/delete any module, regardless of role or other settings
    - `admin` is allowed to use the ViUR administration tool
    - `scriptor` is allowed to use the ViUR scripting features directly within the admin
      This does not affect scriptor actions which are configured for modules, as they allow for
      fine grained usage rule definitions.
    """

    roles: dict[str, str] = {
        "custom": "Custom",
        "user": "User",
        "viewer": "Viewer",
        "editor": "Editor",
        "admin": "Administrator",
    }
    """User roles available on this project.

    The roles can be individually defined per module, see `Module.roles`.

    The default roles can be described as follows:

    - `custom` for users with a custom-settings via the `User.access`-bone; includes root users.
    - `user` for users without any additonal rights. They can log-in and view themselves, or particular modules which
      just check for authenticated users.
    - `viewer` for users who should only view content.
    - `editor` for users who are allowed to edit particular content. They mostly can `view` and `edit`, but not `add`
      or `delete`.
    - `admin` for users with administration privileges. They can edit any data, but still aren't `root`.

    The preset roles are for guidiance, and already fit to most projects.
    """

    session_life_time: datetime.timedelta = datetime.timedelta(hours=1)
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

    redirect_whitelist: list[str] | t.Callable[[], list[str]] = (
        lambda _: ["http://localhost:*", f"https://*{_project_id}.appspot.com*"]
    )
    """Allowed redirect_to patterns for get_cookie_for_app (matched via :func:`fnmatch.fnmatch`).

    The default is a callable that permits only ``http://localhost:*`` and any URL
    containing the current GCP project-ID — a safe built-in policy.
    A zero-argument callable is supported and evaluated on every request.
    Use ``["*"]`` to disable the restriction entirely.

    Examples::

        conf.user.redirect_whitelist = [
            "http://localhost:*",
            "https://*.myapp.appspot.com*",
        ]

        # dynamic / lazily evaluated
        conf.user.redirect_whitelist = lambda: load_whitelist_from_db()
    """

    def __setattr__(self, name: str, value: t.Any) -> None:
        if name == "session_life_time":
            if not isinstance(value, datetime.timedelta):
                from viur.core import utils
                warnings.warn(
                    "Please use timedelta to set session_life_time.",
                    DeprecationWarning, stacklevel=2,
                )
                value = utils.parse.timedelta(value)
        super().__setattr__(name, value)


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

    bone_string_escape_html: bool = True
    """Default escape_html setting for StringBone. Set to False to disable HTML escaping globally."""

    bone_html_default_allow: "HtmlBoneConfiguration" = {
        "validTags": [
            "a",
            "abbr",
            "b",
            "blockquote",
            "br",
            "div",
            "em",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "hr",
            "i",
            "img",
            "li",
            "ol",
            "p",
            "span",
            "strong",
            "sub",
            "sup",
            "table",
            "tbody",
            "td",
            "tfoot",
            "th",
            "thead",
            "tr",
            "u",
            "ul",
        ],
        "validAttrs": {
            "a": [
                "href",
                "target",
                "title",
            ],
            "abbr": [
                "title",
            ],
            "blockquote": [
                "cite",
            ],
            "img": [
                "src",
                "alt",
                "title",
            ],
            "p": [
                "data-indent",
            ],
            "span": [
                "title",
            ],
            "td": [
                "colspan",
                "rowspan",
            ],

        },
        "validStyles": [
            "color",
        ],
        "validClasses": [
            "vitxt-*",
            "viur-txt-*"
        ],
        "singleTags": [
            "br",
            "hr",
            "img",
        ]
    }
    """
    A dictionary containing default configurations for handling HTML content in TextBone instances.
    """

    cache_environment_key: t.Optional[t.Callable[[], str]] = None
    """If set, this function will be called for each cache-attempt
    and the result will be included in the computed cache-key"""

    # FIXME VIUR4: REMOVE ALL COMPATIBILITY MODES!
    compatibility: Multiple[str] = [
        # "json.bone.structure.camelcasenames",  # use camelCase attribute names (see #637 for details)
        # "json.bone.structure.keytuples",  # use classic structure notation: `"structure = [["key", {...}] ...]` (#649)
        # "json.bone.structure.inlists",  # dump skeleton structure with every JSON list response (#774 for details)
        # "tasks.periodic.useminutes",  # Interpret int/float values for @PeriodicTask as minutes
        # #                               instead of seconds (#1133 for details)
        # "bone.select.structure.values.keytuple",  # render old-style tuple-list in SelectBone's
        #                                             values structure (#1203)
    ]
    """Backward compatibility flags; Remove to enforce new style."""

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
        "/viur/src/viur/core/",  # fixme: test suite
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

    tasks_default_queues: dict[str, str] = {
        "__default__": "default",
    }
    """
    @CallDeferred tasks run in the Cloud Tasks Queue "default" by default.
    One way to run them in a different task queue is to use the `_queue` parameter
    when calling the task.
    However, as this is not possible for existing or low-hanging calls,
    default values can be defined here for each task.
    To do this, the task path must be mapped to the queue name:
    ```
    conf.tasks_default_queues["update_relations.viur.core.skeleton"] = "update_relations"
    ```
    The queue (in the example: `"update_relations"`) must exist.
    The default queue can be changed by overwriting `"__default__"`.
    """

    valid_application_ids: list[str] = ["*"]
    """Which application-ids we're supposed to run on"""

    version: tuple[int, int, int] = tuple(int(part) if part.isdigit() else part for part in __version__.split(".", 3))
    """Semantic version number of viur-core as a tuple of 3 (major, minor, patch-level)"""

    viur2import_blobsource: t.Optional[dict[t.Literal["infoURL", "gsdir"], str]] = None
    """Configuration to import file blobs from ViUR2"""

    def __init__(self, strict_mode: bool = False):
        super().__init__()
        self._strict_mode = strict_mode
        self.admin = Admin(parent=self)
        self.db = Database(parent=self)
        self.security = Security(parent=self)
        self.debug = Debug(parent=self)
        self.email = Email(parent=self)
        self.i18n = I18N(parent=self)
        self.user = User(parent=self)
        self.instance = Instance(parent=self)
        self.history = History(parent=self)

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
    strict_mode=os.getenv("VIUR_CORE_CONFIG_STRICT_MODE", "").lower() != "false",
)
