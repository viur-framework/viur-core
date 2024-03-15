"""
    This module implements the WSGI (Web Server Gateway Interface) layer for ViUR. This is the main entry
    point for incomming http requests. The main class is the :class:BrowserHandler. Each request will get it's
    own instance of that class which then holds the reference to the request and response object.
    Additionally, this module defines the RequestValidator interface which provides a very early hook into the
    request processing (useful for global ratelimiting, DDoS prevention or access control).
"""

import json
import logging
import os
import time
import traceback
import typing
import inspect
import unicodedata
import webob
from abc import ABC, abstractmethod
from urllib import parse
from urllib.parse import unquote, urljoin, urlparse
from viur.core import current, db, errors, session, utils
from viur.core.module import Method
from viur.core.config import conf
from viur.core.logging import client as loggingClient, requestLogger, requestLoggingRessource
from viur.core.securityheaders import extendCsp
from viur.core.tasks import _appengineServiceIPs

TEMPLATE_STYLE_KEY = "style"


class RequestValidator(ABC):
    """
        RequestValidators can be used to validate a request very early on. If the validate method returns a tuple,
        the request is aborted. Can be used to block requests from bots.

        To register a new validator, append it to :attr: viur.core.request.BrowseHandler.requestValidators
    """
    # Internal name to trace which validator aborted the request
    name = "RequestValidator"

    @staticmethod
    @abstractmethod
    def validate(request: 'BrowseHandler') -> typing.Optional[typing.Tuple[int, str, str]]:
        """
            The function that checks the current request. If the request is valid, simply return None.
            If the request should be blocked, it must return a tuple of
            - The HTTP status code (as int)
            - The Description of that status code (eg "Forbidden")
            - The Response Body (can be a simple string or an HTML-Page)
        :param request: The Request instance to check
        :return: None on success, an Error-Tuple otherwise
        """
        raise NotImplementedError()


class FetchMetaDataValidator(RequestValidator):
    """
        This validator examines the headers "Sec-Fetch-Site", "sec-fetch-mode" and "sec-fetch-dest" as
        recommended by https://web.dev/fetch-metadata/
    """
    name = "FetchMetaDataValidator"

    @staticmethod
    def validate(request: 'BrowseHandler') -> typing.Optional[typing.Tuple[int, str, str]]:
        headers = request.request.headers
        if not headers.get("sec-fetch-site"):  # These headers are not send by all browsers
            return None
        if headers.get('sec-fetch-site') in {"same-origin", "none"}:  # A Request from our site
            return None
        if os.environ['GAE_ENV'] == "localdev" and headers.get('sec-fetch-site') == "same-site":
            # We are accepting a request with same-site only in local dev mode
            return None
        if headers.get('sec-fetch-mode') == 'navigate' and not request.isPostRequest \
            and headers.get('sec-fetch-dest') not in {'object', 'embed'}:  # Incoming navigation GET request
            return None
        return 403, "Forbidden", "Request rejected due to fetch metadata"


class Router:
    """
        This class accepts the requests, collect its parameters and routes the request
        to its destination function.
        The basic control flow is
        - Setting up internal variables
        - Running the Request validators
        - Emitting the headers (especially the security related ones)
        - Run the TLS check (ensure it's a secure connection or check if the URL is whitelisted)
        - Load or initialize a new session
        - Set up i18n (choosing the language etc)
        - Run the request preprocessor (if any)
        - Normalize & sanity check the parameters
        - Resolve the exposed function and call it
        - Save the session / tear down the request
        - Return the response generated


        :warning: Don't instantiate! Don't subclass! DON'T TOUCH! ;)
    """

    # List of requestValidators used to preflight-check an request before it's being dispatched within ViUR
    requestValidators = [FetchMetaDataValidator]

    def __init__(self, environ: dict):
        super().__init__()
        self.startTime = time.time()

        self.request = webob.Request(environ)
        self.response = webob.Response()

        self.maxLogLevel = logging.DEBUG
        self._traceID = \
            self.request.headers.get("X-Cloud-Trace-Context", "").split("/")[0] or utils.generateRandomString()
        self.is_deferred = False
        self.path_list = ()

        self.skey_checked = False  # indicates whether @skey-decorator-check has already performed within a request
        self.internalRequest = False
        self.disableCache = False  # Shall this request bypass the caches?
        self.pendingTasks = []
        self.args = ()
        self.kwargs = {}
        self.context = {}
        self.template_style: str | None = None

        # Check if it's a HTTP-Method we support
        self.method = self.request.method.lower()
        self.isPostRequest = self.method == "post"
        self.isSSLConnection = self.request.host_url.lower().startswith("https://")  # We have an encrypted channel

        db.currentDbAccessLog.set(set())

        # Set context variables
        current.language.set(conf["viur.defaultLanguage"])
        current.request.set(self)
        current.session.set(session.Session())
        current.request_data.set({})

        # Process actual request
        self._process()

        # Unset context variables
        current.language.set(None)
        current.request_data.set(None)
        current.session.set(None)
        current.request.set(None)
        current.user.set(None)

    @property
    def isDevServer(self) -> bool:
        import warnings
        msg = "Use of `isDevServer` is deprecated; Use `conf[\"viur.instance.is_dev_server\"]` instead!"
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        logging.warning(msg)
        return conf["viur.instance.is_dev_server"]

    def _select_language(self, path: str) -> str:
        """
            Tries to select the best language for the current request. Depending on the value of
            conf["viur.languageMethod"], we'll either try to load it from the session, determine it by the domain
            or extract it from the URL.
        """
        sessionReference = current.session.get()
        if not conf["viur.availableLanguages"]:
            # This project doesn't use the multi-language feature, nothing to do here
            return path
        if conf["viur.languageMethod"] == "session":
            # We store the language inside the session, try to load it from there
            if "lang" not in sessionReference:
                if "X-Appengine-Country" in self.request.headers:
                    lng = self.request.headers["X-Appengine-Country"].lower()
                    if lng in conf["viur.availableLanguages"] + list(conf["viur.languageAliasMap"].keys()):
                        sessionReference["lang"] = lng
                        current.language.set(lng)
                    else:
                        sessionReference["lang"] = conf["viur.defaultLanguage"]
            else:
                current.language.set(sessionReference["lang"])
        elif conf["viur.languageMethod"] == "domain":
            host = self.request.host_url.lower()
            host = host[host.find("://") + 3:].strip(" /")  # strip http(s)://
            if host.startswith("www."):
                host = host[4:]
            if host in conf["viur.domainLanguageMapping"]:
                current.language.set(conf["viur.domainLanguageMapping"][host])
            else:  # We have no language configured for this domain, try to read it from session
                if "lang" in sessionReference:
                    current.language.set(sessionReference["lang"])
        elif conf["viur.languageMethod"] == "url":
            tmppath = urlparse(path).path
            tmppath = [unquote(x) for x in tmppath.lower().strip("/").split("/")]
            if len(tmppath) > 0 and tmppath[0] in conf["viur.availableLanguages"] + list(
                conf["viur.languageAliasMap"].keys()):
                current.language.set(tmppath[0])
                return path[len(tmppath[0]) + 1:]  # Return the path stripped by its language segment
            else:  # This URL doesnt contain an language prefix, try to read it from session
                if "lang" in sessionReference:
                    current.language.set(sessionReference["lang"])
                elif "X-Appengine-Country" in self.request.headers.keys():
                    lng = self.request.headers["X-Appengine-Country"].lower()
                    if lng in conf["viur.availableLanguages"] or lng in conf["viur.languageAliasMap"]:
                        current.language.set(lng)
        return path

    def _process(self):
        if self.method not in ("get", "post", "head"):
            logging.error(f"{self.method=} not supported")
            return

        if self.request.headers.get("X-AppEngine-TaskName", None) is not None:  # Check if we run in the appengine
            if self.request.environ.get("HTTP_X_APPENGINE_USER_IP") in _appengineServiceIPs:
                self.is_deferred = True
            elif os.getenv("TASKS_EMULATOR") is not None:
                self.is_deferred = True

        current.language.set(conf["viur.defaultLanguage"])

        # Check if we should process or abort the request
        for validator, reqValidatorResult in [(x, x.validate(self)) for x in self.requestValidators]:
            if reqValidatorResult is not None:
                logging.warning("Request rejected by validator %s" % validator.name)
                statusCode, statusStr, statusDescr = reqValidatorResult
                self.response.status = '%d %s' % (statusCode, statusStr)
                self.response.write(statusDescr)
                return

        path = self.request.path

        # Add CSP headers early (if any)
        if conf["viur.security.contentSecurityPolicy"] and conf["viur.security.contentSecurityPolicy"]["_headerCache"]:
            for k, v in conf["viur.security.contentSecurityPolicy"]["_headerCache"].items():
                self.response.headers[k] = v
        if self.isSSLConnection:  # Check for HTST and PKP headers only if we have a secure channel.
            if conf["viur.security.strictTransportSecurity"]:
                self.response.headers["Strict-Transport-Security"] = conf["viur.security.strictTransportSecurity"]
        # Check for X-Security-Headers we shall emit
        if conf["viur.security.xContentTypeOptions"]:
            self.response.headers["X-Content-Type-Options"] = "nosniff"
        if conf["viur.security.xXssProtection"] is not None:
            if conf["viur.security.xXssProtection"]:
                self.response.headers["X-XSS-Protection"] = "1; mode=block"
            elif conf["viur.security.xXssProtection"] is False:
                self.response.headers["X-XSS-Protection"] = "0"
        if conf["viur.security.xFrameOptions"] is not None and isinstance(conf["viur.security.xFrameOptions"], tuple):
            mode, uri = conf["viur.security.xFrameOptions"]
            if mode in ["deny", "sameorigin"]:
                self.response.headers["X-Frame-Options"] = mode
            elif mode == "allow-from":
                self.response.headers["X-Frame-Options"] = "allow-from %s" % uri
        if conf["viur.security.xPermittedCrossDomainPolicies"] is not None:
            self.response.headers["X-Permitted-Cross-Domain-Policies"] = conf[
                "viur.security.xPermittedCrossDomainPolicies"]
        if conf["viur.security.referrerPolicy"]:
            self.response.headers["Referrer-Policy"] = conf["viur.security.referrerPolicy"]
        if conf["viur.security.permissionsPolicy"].get("_headerCache"):
            self.response.headers["Permissions-Policy"] = conf["viur.security.permissionsPolicy"]["_headerCache"]
        if conf["viur.security.enableCOEP"]:
            self.response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        if conf["viur.security.enableCOOP"]:
            self.response.headers["Cross-Origin-Opener-Policy"] = conf["viur.security.enableCOOP"]
        if conf["viur.security.enableCORP"]:
            self.response.headers["Cross-Origin-Resource-Policy"] = conf["viur.security.enableCORP"]

        # Ensure that TLS is used if required
        if conf["viur.forceSSL"] and not self.isSSLConnection and not conf["viur.instance.is_dev_server"]:
            isWhitelisted = False
            reqPath = self.request.path
            for testUrl in conf["viur.noSSLCheckUrls"]:
                if testUrl.endswith("*"):
                    if reqPath.startswith(testUrl[:-1]):
                        isWhitelisted = True
                        break
                else:
                    if testUrl == reqPath:
                        isWhitelisted = True
                        break
            if not isWhitelisted:  # Some URLs need to be whitelisted (as f.e. the Tasks-Queue doesn't call using https)
                # Redirect the user to the startpage (using ssl this time)
                host = self.request.host_url.lower()
                host = host[host.find("://") + 3:].strip(" /")  # strip http(s)://
                self.response.status = "302 Found"
                self.response.headers['Location'] = "https://%s/" % host
                return
        if path.startswith("/_ah/warmup"):
            self.response.write("okay")
            return

        try:
            current.session.get().load(self)

            # Load current user into context variable if user module is there.
            if user_mod := getattr(conf["viur.mainApp"], "user", None):
                current.user.set(user_mod.getCurrentUser())

            path = self._select_language(path)[1:]
            if conf["viur.requestPreprocessor"]:
                path = conf["viur.requestPreprocessor"](path)

            self._route(path)

        except errors.Redirect as e:
            if conf["viur.debug.traceExceptions"]:
                logging.warning("""conf["viur.debug.traceExceptions"] is set, won't handle this exception""")
                raise
            self.response.status = '%d %s' % (e.status, e.name)
            url = e.url
            if url.startswith(('.', '/')):
                url = str(urljoin(self.request.url, url))
            self.response.headers['Location'] = url

        except Exception as e:
            if conf["viur.debug.traceExceptions"]:
                logging.warning("""conf["viur.debug.traceExceptions"] is set, won't handle this exception""")
                raise
            self.response.body = b""
            if isinstance(e, errors.HTTPException):
                logging.info(f"[{e.status}] {e.name}: {e.descr}", exc_info=conf["viur.debug.trace"])
                self.response.status = '%d %s' % (e.status, e.name)
                # Set machine-readable x-viur-error response header in case there is an exception description.
                if e.descr:
                    self.response.headers["x-viur-error"] = e.descr.replace("\n", "")
            else:
                self.response.status = 500
                logging.error("ViUR has caught an unhandled exception!")
                logging.exception(e)

            res = None
            if conf["viur.errorHandler"]:
                try:
                    res = conf["viur.errorHandler"](e)
                except Exception as newE:
                    logging.error("viur.errorHandler failed!")
                    logging.exception(newE)
                    res = None
            if not res:
                descr = "The server encountered an unexpected error and is unable to process your request."

                if isinstance(e, errors.HTTPException):
                    error_info = {
                        "status": e.status,
                        "reason": e.name,
                        "title": str(translate(e.name)),
                        "descr": e.descr,
                    }
                else:
                    error_info = {
                        "status": 500,
                        "reason": "Internal Server Error",
                        "title": str(translate("Internal Server Error")),
                        "descr": descr
                    }

                if conf["viur.instance.is_dev_server"]:
                    error_info["traceback"] = traceback.format_exc()

                if (len(self.path_list) > 0 and self.path_list[0] in ("vi", "json")) or \
                        current.request.get().response.headers["Content-Type"] == "application/json":
                    current.request.get().response.headers["Content-Type"] = "application/json"
                    res = json.dumps(error_info)
                else:  # We render the error in html
                    # Try to get the template from html/error/
                    if filename := conf["viur.mainApp"].render.getTemplateFileName((f"{error_info['status']}", "error"),
                                                                                   raise_exception=False):
                        template = conf["viur.mainApp"].render.getEnv().get_template(filename)
                        res = template.render(error_info)

                        # fixme: this might be the viur/core/template/error.html ...
                        extendCsp({"style-src": ['sha256-Lwf7c88gJwuw6L6p6ILPSs/+Ui7zCk8VaIvp8wLhQ4A=']})
                    else:
                        res = f"""<html><h1>{error_info["status"]} - {error_info["reason"]}"""

            self.response.write(res.encode("UTF-8"))

        finally:
            self.saveSession()
            if conf["viur.instance.is_dev_server"] and conf["viur.dev_server_cloud_logging"]:
                # Emit the outer log only on dev_appserver (we'll use the existing request log when live)
                SEVERITY = "DEBUG"
                if self.maxLogLevel >= 50:
                    SEVERITY = "CRITICAL"
                elif self.maxLogLevel >= 40:
                    SEVERITY = "ERROR"
                elif self.maxLogLevel >= 30:
                    SEVERITY = "WARNING"
                elif self.maxLogLevel >= 20:
                    SEVERITY = "INFO"

                TRACE = "projects/{}/traces/{}".format(loggingClient.project, self._traceID)

                REQUEST = {
                    'requestMethod': self.request.method,
                    'requestUrl': self.request.url,
                    'status': self.response.status_code,
                    'userAgent': self.request.headers.get('USER-AGENT'),
                    'responseSize': self.response.content_length,
                    'latency': "%0.3fs" % (time.time() - self.startTime),
                    'remoteIp': self.request.environ.get("HTTP_X_APPENGINE_USER_IP")
                }
                requestLogger.log_text(
                    "",
                    client=loggingClient,
                    severity=SEVERITY,
                    http_request=REQUEST,
                    trace=TRACE,
                    resource=requestLoggingRessource,
                    operation={
                        "first": True,
                        "last": True,
                        "id": self._traceID
                    }
                )

        if conf["viur.instance.is_dev_server"]:
            self.is_deferred = True

            while self.pendingTasks:
                task = self.pendingTasks.pop()
                logging.debug(f"Deferred task emulation, executing {task=}")
                task()

    def _route(self, path: str) -> None:
        """
            Does the actual work of sanitizing the parameter, determine which exposed-function to call
            (and with which parameters)
        """

        # Parse the URL
        if path := parse.urlparse(path).path:
            self.path_list = tuple(unicodedata.normalize("NFC", parse.unquote(part))
                                   for part in path.strip("/").split("/"))

        # Prevent Hash-collision attacks
        if len(self.request.params) > conf["viur.maxPostParamsCount"]:
            raise errors.BadRequest(
                f"Too many arguments supplied, exceeding maximum"
                f" of {conf['viur.maxPostParamsCount']} allowed arguments per request"
            )

        param_filter = conf["viur.paramFilterFunction"]
        if param_filter and not callable(param_filter):
            raise ValueError(f"""{param_filter=} is not callable""")

        for key, value in self.request.params.items():
            try:
                key = unicodedata.normalize("NFC", key)
                value = unicodedata.normalize("NFC", value)
            except UnicodeError:
                # We received invalid unicode data (usually happens when
                # someone tries to exploit unicode normalisation bugs)
                raise errors.BadRequest()

            if param_filter and param_filter(key, value):
                continue

            if key == TEMPLATE_STYLE_KEY:
                self.template_style = value
                continue

            if key in self.kwargs:
                if isinstance(self.kwargs[key], list):
                    self.kwargs[key].append(value)
                else:  # Convert that key to a list
                    self.kwargs[key] = [self.kwargs[key], value]
            else:
                self.kwargs[key] = value

        if "self" in self.kwargs or "return" in self.kwargs:  # self or return is reserved for bound methods
            raise errors.BadRequest()

        caller = conf["viur.mainResolver"]
        idx = 0  # Count how may items from *args we'd have consumed (so the rest can go into *args of the called func
        path_found = True

        for part in self.path_list:
            # TODO: Remove canAccess guards... solve differently.
            if "canAccess" in caller and not caller["canAccess"]():
                # We have a canAccess function guarding that object,
                # and it returns False...
                raise errors.Unauthorized()

            idx += 1
            part = part.replace("-", "_")
            if part not in caller:
                part = "index"

            # print(part, caller.get(part))

            if caller := caller.get(part):
                if isinstance(caller, Method):
                    if part == "index":
                        idx -= 1

                    self.args = tuple(self.path_list[idx:])
                    break

                elif part == "index":
                    path_found = False
                    break

            else:
                path_found = False
                break

        if not path_found:
            raise errors.NotFound(
                f"""The path {utils.escapeString("/".join(self.path_list[:idx]))} could not be found""")

        if not isinstance(caller, Method):
            # try to find "index" function
            if (index := caller.get("index")) and isinstance(index, Method):
                caller = index
            else:
                raise errors.MethodNotAllowed()

        # Check for internal exposed
        if caller.exposed is False and not self.internalRequest:
            raise errors.NotFound()

        # Check for @force_ssl flag
        if not self.internalRequest \
                and caller.ssl \
                and not self.request.host_url.lower().startswith("https://") \
                and not conf["viur.instance.is_dev_server"]:
            raise errors.PreconditionFailed("You must use SSL to access this resource!")

        # Check for @force_post flag
        if not self.isPostRequest and caller.methods == ("POST", ):
            raise errors.MethodNotAllowed("You must use POST to access this resource!")

        # Check if this request should bypass the caches
        if self.request.headers.get("X-Viur-Disable-Cache"):
            # No cache requested, check if the current user is allowed to do so
            if (user := current.user.get()) and "root" in user["access"]:
                logging.debug("Caching disabled by X-Viur-Disable-Cache header")
                self.disableCache = True

        # Destill context as self.context, if available
        if context := {k: v for k, v in self.kwargs.items() if k.startswith("@")}:
            # Remove context parameters from kwargs
            kwargs = {k: v for k, v in self.kwargs.items() if k not in context}
            # Remove leading "@" from context parameters
            self.context |= {k[1:]: v for k, v in context.items() if len(k) > 1}
        else:
            kwargs = self.kwargs

        if ((self.internalRequest and conf["viur.debug.traceInternalCallRouting"])
                or conf["viur.debug.traceExternalCallRouting"]):
            logging.debug(
                f"Calling {caller._func!r} with args={self.args!r}, {kwargs=} within context={self.context!r}"
            )

        # Now call the routed method!
        res = caller(*self.args, **kwargs)

        if not isinstance(res, bytes):  # Convert the result to bytes if it is not already!
            res = str(res).encode("UTF-8")

        self.response.write(res)

    def saveSession(self) -> None:
        current.session.get().save(self)


from .i18n import translate  # noqa: E402
