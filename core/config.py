# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
#from google.appengine.ext import db
#from google.appengine.api import memcache
import sys

apiVersion = 1  # What format do we use to store data in the bigtable

# Conf is static, local Dictionary. Changes here are local to the current instance
conf = {
	# Accessrights available on this Application
	"viur.accessRights": ["root", "admin"],
	# List of language-codes, which are valid for this application
	"viur.availableLanguages": ["en"],

	# If set, this function will be called for each cache-attempt and the result will be included in
	# the computed cache-key
	"viur.cacheEnvironmentKey": None,

	# Extended functionality of the whole System (For module-dependend functionality advertise this in
	# the module configuration (adminInfo)
	"viur.capabilities": [],

	# If set, viur will emit a CSP http-header with each request. Use the csp module to set this property
	"viur.contentSecurityPolicy": None,

	# Cache strategy used by the database. 2: Aggressive, 1: Safe, 0: Off
	"viur.db.caching": 2,

	# If enabled, user-generated exceptions from the server.errors module won't be caught and handled
	"viur.debug.traceExceptions": False,
	# If enabled, ViUR will log which (exposed) function are called from outside with what arguments
	"viur.debug.traceExternalCallRouting": False,
	# If enabled, ViUR will log which (internal-exposed) function are called from templates with what arguments
	"viur.debug.traceInternalCallRouting": False,
	# If enabled, we log all datastore queries performed
	"viur.debug.traceQueries": False,

	# Unless overridden by the Project: Use english as default language
	"viur.defaultLanguage": "en",
	# If set to true, the decorator @enableCache from viur.core.cache has no effect
	"viur.disableCache": False,
	# Maps Domains to alternative default languages
	"viur.domainLanguageMapping": {},
	# For how long we'll keep successfully send emails in the viur-emails table
	"viur.email.logRetention": timedelta(days=30),
	# Class that actually delivers the email using the service provider of choice. See email.py for more details
	"viur.email.transportClass": None,
	# If set, we'll enable sending emails from the local development server. Otherwise, they'll just be logged.
	"viur.email.sendFromLocalDevelopmentServer": False,
	# If set, all outgoing emails will be send to this address (overriding the 'dests'-parameter in utils.sendEmail)
	"viur.email.recipientOverride": None,
	# If set, this sender will be used, regardless of what the templates advertise as sender
	"viur.email.senderOverride": None,

	# If set, ViUR call this function instead of rendering the viur.errorTemplate if an exception occurs
	"viur.errorHandler": None,
	# Path to the template to render if an unhandled error occurs. This is a Python String-template, *not* a jinja2 one!
	"viur.errorTemplate": "viur/core/template/error.html",

	# Path to the static SVGs folder. Will be used by the jinja-renderer-method: embedSvg
	"viur.static.embedSvg.path": "/static/svgs/",

	# Activates the Database export API if set. Must be exactly 32 chars. *Everyone* knowing this password can dump the whole database!
	"viur.exportPassword": None,
	# Activates the Database import API if set. Must be exactly 32 chars. *Everyone* knowing this password can rewrite the whole database!
	"viur.importPassword": None,

	# If true, all requests must be encrypted (ignored on development server)
	"viur.forceSSL": True,

	# Hmac-Key used to sign download urls - set automatically
	"viur.file.hmacKey": None,
	# Call-Map for file preprocessers
	"viur.file.derivers": {},

	# Allows mapping of certain languages to one translation (ie. us->en)
	"viur.languageAliasMap": {},
	# Defines how translations are applied. session: Per Session, url: inject language prefix in url, domain: one domain per language
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

	# List of Urls for which viur.forceSSL is ignored. Add an asterisk to mark that entry as a prefix (exact match otherwise)
	"viur.noSSLCheckUrls": ["/_tasks*", "/ah/*"],

	# Allows the application to register a function that's called before the request gets routed
	"viur.requestPreprocessor": None,

	# Characters valid for the internal search functionality (all other chars are ignored)
	"viur.searchValidChars": "abcdefghijklmnopqrstuvwxyz0123456789",

	# If set, viur will emit a CSP http-header with each request. Use security.addCspRule to set this property
	"viur.security.contentSecurityPolicy": {
		'enforce': {
			'style-src': ['self', 'unsafe-inline'],  # unsafe-inline currently required for textBones
			'default-src': ['self'],
			'img-src': ['self', '*.ggpht.com', '*.googleusercontent.com'],  # Serving-URLs of file-Bones will point here
			'script-src': ['self'],
			# Required to login with google:
			'frame-src': ['self', 'www.google.com', 'drive.google.com', 'accounts.google.com']
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
	"viur.security.enableCOEP": True,
	# Emit a Cross-Origin-Opener-Policy Header? Valid values are same-origin|same-origin-allow-popups|unsafe-none
	"viur.security.enableCOOP": "same-origin",
	# Emit a Cross-Origin-Resource-Policy Header? Valid values are same-site|same-origin|cross-origin
	"viur.security.enableCORP": "same-origin",
	# If set, viur will emit a HSTS http-header with each request. Use security.enableStrictTransportSecurity to set this property
	"viur.security.strictTransportSecurity": None,
	# If set, ViUR will emit a X-Frame-Options header,
	"viur.security.xFrameOptions": ("sameorigin", None),
	# ViUR will emit a X-XSS-Protection header if set (the default),
	"viur.security.xXssProtection": True,
	# ViUR will emit X-Content-Type-Options: nosniff Header unless set to False
	"viur.security.xContentTypeOptions": True,
	# Unless set to logical none; ViUR will emit a X-Permitted-Cross-Domain-Policies with each request
	"viur.security.xPermittedCrossDomainPolicies": "none",

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

	# Will be set to server.__version__ in server.__init__
	"viur.version": None,
}
