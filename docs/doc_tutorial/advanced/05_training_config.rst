-------------
Configuration
-------------
The module ``config`` provided by the ViUR server contains several configuration options which change the
servers behavior, allowing you to access system-global parameters, or provide some kind of global variables
within a ViUR project setup.
It simply can be imported into any server-side module with

::

    from server.config import conf

All ViUR-specific parameters have the prefix **viur.**. Parameters that influence or extend information
used by the Admin-tools start with the prefix **admin.** or more specialized with **admin.vi.**.
If parameters are changed for configuration issues, this should be done on the server's main entry (i.e. that
Python source file that calls ``viur.core.run()``).

This section gives an overview and detailed information about how to use ViURs pre-defined configuration
parameters.


Server configuration
--------------------

viur.accessRights
.................
Defines a list of default user access rights. Defaults to ``["admin", "root"]``.

This list can be extended to project-specific access rights that are made available to every user
entity created by the user module. By default, there exists two entries which are

- *admin* defines if the user has admin-access (ie. is allowed to access the admin and vi render)
- *root* defines if the user is a super-admin (users having the root-flag are allowed to do anything by default)

These entries can be enriched in the application's main entry with

::

    conf["viur.accessRights"].append("myProjectFlag")

Each module in your application will register the flags it supports during startup, so make sure you use *.append* to add
your flags instead of (re)-setting this property


viur.availableLanguages
.......................
Defines a list of valid language-codes. These are the languages that are available on projects with multi-language setup.
Unless it's white-listed here, ViUR will refuse to serve requests in that language.
The language code also defines the name of the language translation file in the *translations*
folder of the project.

Example configuration:
::

    conf["viur.availableLanguages"] = ["de", "en", "fr"] # German, English, French.

See also `viur.defaultLanguage`_, `viur.domainLanguageMapping`_, `viur.languageMethod`_
and `viur.logMissingTranslations`_.

.. Hint::
    If translation is not working despite having *viur.availableLanguages* set, check that your *projects*-tranlation
    module is importable and contains an translation table for that language. If your translation-module is not importable,
    all i18n features are disabled!


viur.cacheEnvironmentKey
........................
Call this function for each time we need to derive a key for caching.

If the configuration parameter *viur.cacheEnvironmentKey* contains a callable, this function will be
called for each cache-attempt and the result will be included in the computed cache-key. This allows you to
easily include environment variables like the current language into the key used to determine the caching-slot.


viur.capabilities
.................
Reserved for further use.

Can be used to advertise system-wide addons to modules.


viur.contentSecurityPolicy
..........................
Emit Content-Security-Policy HTTP-header with each request.

Use :meth:`viur.core.securityheaders.addCspRule` to modify this property.


viur.db.caching
...............
Defines a caching strategy that is used by the database API to reduce read-requests on cloud-databases
like Google Datastore. We recommend to leave this set to *2*. See :doc:`/doc_guide/05_implementation_consistency`.

- 2: Aggressive mode (default)
- 1: Safe mode
- 0: Turns optimization off


viur.debug.traceExceptions
..........................
Disable catch and handling of user-generated http-exceptions. Useful to trace where a Redirect or Forbidden etc. error
is raised inside deeply nested code.


viur.debug.traceExternalCallRouting
...................................
Logging calls of any functions marked as exposed. It will write the called function name and it's parameter to the log.

.. Warning::

    This might include sensitive data like unencrypted usernames and passwords in your log! Keep it off in production!


viur.debug.traceInternalCallRouting
...................................
Logging calls of any functions marked as internalExposed. It will write the called function name and it's parameter to the log.

.. Warning::

    This might include sensitive data like unencrypted usernames and passwords in your log! Keep it off in production!


viur.debug.traceQueries
.......................
Logging of datastore queries.

If enabled, ViUR will write each query run against the datastore into the log - including it's kind, filters and orders.


viur.defaultLanguage
....................
Default language used by the project, if no other language code was specified.

Unless overridden, english ("en") will be used as the default language.

See also `viur.availableLanguages`_, `viur.domainLanguageMapping`_, `viur.languageMethod`_
and `viur.logMissingTranslations`_.


viur.disableCache
.................
If set True, the decorator @enableCache from server.cache has no effect. Caching inside the jinja2 Render will also
be disabled.

.. Note::

    This doesn't cause entries already in the cache to be evicted. If they're old entries they just won't be used and no
    new entries will be added. Once that property is set to false again, old entries in the cache will be served again
    if they haven't expired yet.


viur.domainLanguageMapping
..........................
Map domains to alternative default languages.

See also `viur.availableLanguages`_, `viur.defaultLanguage`_, `viur.languageMethod`_
and `viur.logMissingTranslations`_.


viur.emailRecipientOverride
...........................
Override recipients for all outgoing email. This should be done for testing purposes only.

If set, all outgoing emails will be send to this address
(always overriding the *dests*-parameter in `viur.core.utils.sendEmail`_).

::

    conf["viur.emailRecipientOverride"] = "john@doe.net" # Simple override
    conf["viur.emailRecipientOverride"] = ["john@doe.net", "max@mustermann.de"] # Override to multiple targets
    conf["viur.emailRecipientOverride"] = "@viur.dev" # Redirect all emails to this domain. "me@gmail.com" would become "me_at_gmail_dot_com@viur.is"
    conf["viur.emailRecipientOverride"] = False # Entirely disable sending emails.
    conf["viur.emailRecipientOverride"] = None # Default, outgoing email go to the specified recipients.


See also `viur.emailSenderOverride`_.


viur.emailSenderOverride
........................
Override the sender of all outgoing emails by this one.

If set, this sender will be used, regardless of what the templates advertise as sender.

::

    conf["viur.emailSenderOverride"] = "john@doe.net" # Simple override
    conf["viur.emailSenderOverride"] = "John Doe <john@doe.net>" # Override with name
    conf["viur.emailSenderOverride"] = None # No override (default)


See also `viur.emailRecipientOverride`_.


viur.errorHandler
.................
Defines a custom error handler. If set, ViUR calls this function instead of rendering the
`viur.errorTemplate`_ in case of exception.

The function must accept one argument (an instance of the Python exception object (possibly an instance of
`viur.core.errors.HTTPException`_), in case that an HTTP-exception occurs).


viur.errorTemplate
..................
Defines a custom error template. This is a path to the template to render if an unhandled error occurs.

This is a Python String-template, *not* a Jinja2 one! Might have no effect if `viur.errorHandler` is set.


viur.exportPassword
...................
Activates the database export API if set.

Must be exactly 32 chars. *Everyone knowing this password can dump the entire database!*


viur.forceSSL
.............
Enable HTTPS enforcement.

::

    config["viur.forceSSL"] = True # We want to be secure!

If set True, all requests must be encrypted (ignored on development server). If unencrypted requests are received,
a redirect to https://your.domain/ is raised (the path and request paremeters are *not* preserved for security reasons).


viur.importPassword
...................
Activates the database import API if set.

Must be exactly 32 chars.

.. Warning::
    *Everyone knowing this password can overwrite the entire database!* Never use in a production environment.

    ViUR will bug you repeatedly until you turn it off.


viur.languageAliasMap
.....................
Defines a mapping for certain languages directing to one translation (ie. us->en).


viur.languageMethod
...................
Method of how translation is applied.
By default, this is configured to "session".

- *session* saves within session (default)
- *url* injects a language prefix into the URL
- *domain* configures one domain per language


viur.logMissingTranslations
...........................
Silently log missing translations during application run.
If ViUR encounters an missing translation, it logs it by creating an entry in the *viur-missing-translations* kind.


viur.mainApp
............
Holds a reference to the pre-build application-instance that's created by ``viur.core.run()``.
**May not be overridden, reassigned or modified!**


viur.maxPasswordLength
......................
Defines a maximum password length. This prevents denial of service attacks through large inputs for pbkdf2.
The value defaults to 512.


viur.maxPostParamsCount
.......................
Upper limit of the amount of parameters accepted per request. Prevents Hash-Collision-Attacks. The value defaults to 250.


viur.models
...........
Holds a dictionary of all models.
**May not be overridden, reassigned or modified!**


viur.noSSLCheckUrls
...................
Disable the `viur.forceSSL`_ restriction for certain URLs (ie these URLs will be also accessible and served over
unencrypted http). Add an asterisk to whitelist an entire prefix (exact match otherwise).

It defaults to ``["/_tasks*", "/ah/*"]`` as the task-queue doesn't call using https.



viur.requestPreprocessor
........................
Attach a request preprocessor to the application.

A preprocesser is a function receiving the original path from the URL requested and might rewrite it before its used
by ViUR to determine which function in the application should be called. Can also be used to run custom code on each
request before it's normally dispatched to your application.


viur.salt
.........
Default salt used for passwords.

.. deprecated:: 0.8 **Don't change.** Will be removed in a future version. Salts are now randomly
    chosen for each password and stored along with the hash inside the datastore.


viur.searchValidChars
.....................
Characters valid for the internal search functionality (all other characters are ignored). If changed you must rebuild
all search-indexes for skeletons that don't use the search api provided by the appengine (ie all skeletons where
*searchIndex* is None)


viur.security.contentSecurityPolicy
...................................
If set, viur will emit a CSP http-header with each request.

Use :meth:`viur.core.securityheaders.addCspRule` to set this property.


viur.security.strictTransportSecurity
.....................................
If set, viur will emit a HSTS http-header with each request.

Use :meth:`viur.core.securityheaders.enableStrictTransportSecurity` to set this property. Only partially supported on the Appengine atm.


viur.security.publicKeyPins
...........................
If set, viur will emit a Public Key Pins http-header with each request.

Use :meth:`securityheaders.setPublicKeyPins` to set this property.

.. Note:: This is reserved for further use. It's not yet supported on the appengine.



viur.security.xFrameOptions
...........................
If set, ViUR will emit a X-Frame-Options header.

Use :meth:`viur.core.securityheaders.setXFrameOptions` to set this property.

viur.security.xXssProtection
............................
ViUR will emit a X-XSS-Protection header if set (the default).

Use :meth:`securityheaders.setXXssProtection` to set this property.


viur.security.xContentTypeOptions
.................................
ViUR will emit *X-Content-Type-Options: nosniff* Header unless set to False.

Use :meth:`securityheaders.setXContentTypeNoSniff` to set this property.


viur.session.lifeTime
.....................
Specifies when sessions timeout.

The value must be given in seconds. Defaults to 60 minutes.
If no request is received within that window, the session is terminated and the user will have to login again.


viur.session.persistentFieldsOnLogin
....................................
Preserve session values on login.

For security reasons, the session is reset when a user logs in. Only fields specified in this list will be kept on login.

::

    from server import session, config
    config["viur.session.persistentFieldsOnLogin"] = ["username"]

    session.current["username"] = "john" # Will be kept after logging in
    session.current["password"] = "secret" # Will be lost after logging in
    session.current.markChanged()


viur.session.persistentFieldsOnLogout
.....................................
Preserve session values on logout.

For security reasons, the session is reset when a user logs out. Only fields specified in this list will be kept.

For example, see `viur.session.persistentFieldsOnLogin`_.


viur.tasks.customEnvironmentHandler
...................................
Preserve additional environment in deferred tasks.

If set, must be a tuple of two functions (serializeEnv, restoreEnv) for serializing/restoring your enviromental data.
The serializeEnv function must not accept any parameter and return and json-serializable object with the information
you need to preserve. The restoreEnv function receives that object and should write the information contained therein
into the environment of that deferred request.


Admin configuration
-------------------

admin.moduleGroups
..................
Grouping modules within panes.

It is possible to group different modules into logical panes, so they share a single entry in the admin.
This is done by choosing a prefix, which will be used to group the different modules.

::

    conf[ "admin.moduleGroups" ] = [
       {"prefix":"Tea: ", "name": "Tea", "icon": "icons/modules/produktdatenbank.png" },
    ]


This example will add all modules, which descriptions starts with the prefix *Tea:* to the group *Tea*
with the given icon.

admin.vi.name
.............
Specifies a custom name in the vi admin.

::

    conf["admin.vi.name"] = u"Admin"

admin.vi.logo
.............
Specifies a custom logo in the vi admin.

::

    conf["admin.vi.logo"] = "/static/meta/project-logo.svg"


Miscellaneous configuration
---------------------------

bugsnag.apiKey
..............
ViUR has integrated support for bugsnag.

To enable reporting to bugsnag, just set your personal bugsnag API-Key,
the rest will be determined automatically.

::

    conf["bugsnag.apiKey"] = "your api key"
