import os
import datetime
import hashlib
import logging
import warnings
import google.auth
from viur.core.version import __version__


class Conf(dict):
    """
    Conf class wraps the conf dict and allows to handle deprecated keys or other special operations.
    """

    def __getitem__(self, key):
        # VIUR3.3: Handle deprecations...
        match key:
            case "viur.downloadUrlFor.expiration":
                msg = f"{key!r} was substituted by `viur.render.html.downloadUrlExpiration`"
                warnings.warn(msg, DeprecationWarning, stacklevel=3)
                logging.warning(msg, stacklevel=3)

                key = "viur.render.html.downloadUrlExpiration"

        return super().__getitem__(key)

    def __setitem__(self, key, value):
        # VIUR3.3: Handle deprecations...
        match key:
            case "viur.downloadUrlFor.expiration":
                raise ValueError(f"{key!r} was replaced by `viur.render.html.downloadUrlExpiration`, please fix!")

        # Avoid to set conf values to something which is already the default
        if key in self and self[key] == value:
            msg = f"Setting conf[\"{key}\"] to {value!r} has no effect, as this value has already been set"
            warnings.warn(msg, stacklevel=3)
            logging.warning(msg, stacklevel=3)
            return

        super().__setitem__(key, value)


# Some values used more than once below
__project_id = google.auth.default()[1]
__version = os.getenv("GAE_VERSION")

# Conf is a static, local dictionary.
# Changes here apply locally to the current instance only.

conf = Conf({
    # Administration tool configuration
    "admin.name": "ViUR",

    # URL for the Logo in the Topbar of the VI
    "admin.logo": "",

    # URL for the big Image in the background of the VI Login screen
    "admin.login.background": "",

    # URL for the Logo over the VI Login screen
    "admin.login.logo": "",

    # primary color for the  VI
    "admin.color.primary": "#d00f1c",

    # secondary color for the  VI
    "admin.color.secondary": "#333333",

    # Additional access rights available on this project
    "viur.accessRights": ["root", "admin"],

    # List of language-codes, which are valid for this application
    "viur.availableLanguages": ["en"],

    # Allowed values that define a str to evaluate to true
    "viur.bone.boolean.str2true": ("true", "yes", "1"),

    # If set, this function will be called for each cache-attempt and the result will be included in
    # the computed cache-key
    "viur.cacheEnvironmentKey": None,

    # If set, viur will emit a CSP http-header with each request. Use the csp module to set this property
    "viur.contentSecurityPolicy": None,

    # Database engine module
    "viur.db.engine": "viur.datastore",

    # If enabled, user-generated exceptions from the viur.core.errors module won't be caught and handled
    "viur.debug.traceExceptions": False,
    # If enabled, ViUR will log which (exposed) function are called from outside with what arguments
    "viur.debug.traceExternalCallRouting": False,
    # If enabled, ViUR will log which (internal-exposed) function are called from templates with what arguments
    "viur.debug.traceInternalCallRouting": False,
    # If enabled, log errors raises from skeleton.fromClient()
    "viur.debug.skeleton.fromClient": False,

    # Unless overridden by the Project: Use english as default language
    "viur.defaultLanguage": "en",

    # If set to true, the decorator @enableCache from viur.core.cache has no effect
    "viur.disableCache": False,

    # Maps Domains to alternative default languages
    "viur.domainLanguageMapping": {},

    # For how long we'll keep successfully send emails in the viur-emails table
    "viur.email.logRetention": datetime.timedelta(days=30),

    # Class that actually delivers the email using the service provider of choice. See email.py for more details
    "viur.email.transportClass": None,

    # If set, we'll enable sending emails from the local development server. Otherwise, they'll just be logged.
    "viur.email.sendFromLocalDevelopmentServer": False,

    # If set, all outgoing emails will be sent to this address (overriding the 'dests'-parameter in utils.sendEmail)
    "viur.email.recipientOverride": None,

    # If set, this sender will be used, regardless of what the templates advertise as sender
    "viur.email.senderOverride": None,

    # If set, ViUR calls this function instead of rendering the viur.errorTemplate if an exception occurs
    "viur.errorHandler": None,

    # Path to the template to render if an unhandled error occurs. This is a Python String-template, *not* Jinja
    "viur.errorTemplate": "viur/core/template/error.html",

    # Path to the static SVGs folder. Will be used by the jinja-renderer-method: embedSvg
    "viur.static.embedSvg.path": "/static/svgs/",

    # If true, all requests must be encrypted (ignored on development server)
    "viur.forceSSL": True,

    # Hmac-Key used to sign download urls - set automatically
    "viur.file.hmacKey": None,

    # Call-Map for file pre-processors
    "viur.file.derivers": {},

    # Determine whether instance is running on a local development server
    "viur.instance.is_dev_server": os.getenv("GAE_ENV") == "localdev",

    # The instance's project ID
    "viur.instance.project_id": __project_id,

    # Name of this version as deployed to the appengine
    "viur.instance.app_version": __version,

    # Version hash that does not reveal the actual version name, can be used for cache-busting static resources
    "viur.instance.version_hash": hashlib.sha256((__version + __project_id).encode("UTF-8")).hexdigest()[:10],

    # Allows mapping of certain languages to one translation (ie. us->en)
    "viur.languageAliasMap": {},

    # Defines how translations are applied:
    # - session: Per Session
    # - url: inject language prefix in url
    # - domain: one domain per language
    "viur.languageMethod": "session",

    # Maps modules to their translation (if set)
    "viur.languageModuleMap": {},

    # If true, ViUR will log missing translations in the datastore
    "viur.logMissingTranslations": False,

    # Reference to our pre-build Application-Instance
    "viur.mainApp": None,

    # Dictionary for Resolving functions for URLs
    "viur.mainResolver": None,

    # Prevent Denial of Service attacks using large inputs for pbkdf2
    "viur.maxPasswordLength": 512,

    # Upper limit of the amount of parameters we accept per request. Prevents Hash-Collision-Attacks
    "viur.maxPostParamsCount": 250,

    # Describing the internal ModuleConfig-module
    "viur.moduleconf.admin_info": {
        "name": "Module Configuration",
        "icon": "icon-settings",
        "display": "hidden",
    },

    # List of URLs for which viur.forceSSL is ignored.
    # Add an asterisk to mark that entry as a prefix (exact match otherwise)
    "viur.noSSLCheckUrls": ["/_tasks*", "/ah/*"],

    # The default duration, for which downloadURLs generated by the html renderer will stay valid
    "viur.render.html.downloadUrlExpiration": None,

    # The default duration, for which downloadURLs generated by the json renderer will stay valid
    "viur.render.json.downloadUrlExpiration": None,

    # Allows the application to register a function that's called before the request gets routed
    "viur.requestPreprocessor": None,

    # Characters valid for the internal search functionality (all other chars are ignored)
    "viur.searchValidChars": "abcdefghijklmnopqrstuvwxyzäöüß0123456789",

    # If set, viur will emit a CSP http-header with each request. Use security.addCspRule to set this property
    "viur.security.contentSecurityPolicy": {
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
    },

    # Per default, we'll emit Referrer-Policy: strict-origin so no referrers leak to external services
    "viur.security.referrerPolicy": "strict-origin",

    # Include a default permissions-policy. To use the camera or microphone, you'll have to call
    # :meth: securityheaders.setPermissionPolicyDirective to include at least "self"
    "viur.security.permissionsPolicy": {
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
    },

    # Shall we emit Cross-Origin-Embedder-Policy: require-corp?
    "viur.security.enableCOEP": False,

    # Emit a Cross-Origin-Opener-Policy Header?
    # Valid values are same-origin|same-origin-allow-popups|unsafe-none
    "viur.security.enableCOOP": "same-origin",

    # Emit a Cross-Origin-Resource-Policy Header?
    # Valid values are same-site|same-origin|cross-origin
    "viur.security.enableCORP": "same-origin",

    # If set, ViUR will emit a HSTS HTTP-header with each request.
    # Use security.enableStrictTransportSecurity to set this property
    "viur.security.strictTransportSecurity": "max-age=22118400",

    # If set, ViUR will emit an X-Frame-Options header,
    "viur.security.xFrameOptions": ("sameorigin", None),

    # ViUR will emit an X-XSS-Protection header if set (the default),
    "viur.security.xXssProtection": True,

    # ViUR will emit X-Content-Type-Options: nosniff Header unless set to False
    "viur.security.xContentTypeOptions": True,

    # Unless set to logical none; ViUR will emit a X-Permitted-Cross-Domain-Policies with each request
    "viur.security.xPermittedCrossDomainPolicies": "none",

    # The default sitekey and secret to use for the captcha-bone. If set, must be a dictionary of "sitekey" and "secret"
    "viur.security.captcha.defaultCredentials": None,

    # Default is 60 minutes lifetime for ViUR sessions
    "viur.session.lifeTime": 60 * 60,

    # If set, these Fields will survive the session.reset() called on user/login
    "viur.session.persistentFieldsOnLogin": [],

    # If set, these Fields will survive the session.reset() called on user/logout
    "viur.session.persistentFieldsOnLogout": [],

    # Priority, in which skeletons are loaded
    "viur.skeleton.searchPath": ["/skeletons/", "/viur/core/"],  # Priority, in which skeletons are loaded

    # If set, must be a tuple of two functions serializing/restoring additional environmental data in deferred requests
    "viur.tasks.customEnvironmentHandler": None,

    # Which application-ids we're supposed to run on
    "viur.validApplicationIDs": [],

    # Semantic version number of viur-core as a tuple of 3 (major, minor, patch-level)
    "viur.version": tuple(__version__.split(".", 3)),
})
