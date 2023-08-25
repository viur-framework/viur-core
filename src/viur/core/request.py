import json
import logging
import os
import time
import traceback
import typing
import inspect
import unicodedata
from abc import ABC, abstractmethod
from urllib import parse
from urllib.parse import unquote, urljoin, urlparse

import webob

from viur.core import current, db, errors, utils
from viur.core.config import conf
from viur.core.logging import client as loggingClient, requestLogger, requestLoggingRessource
from viur.core.securityheaders import extendCsp
from viur.core.tasks import _appengineServiceIPs

"""
    This module implements the WSGI (Web Server Gateway Interface) layer for ViUR. This is the main entry
    point for incomming http requests. The main class is the :class:BrowserHandler. Each request will get it's
    own instance of that class which then holds the reference to the request and response object.
    Additionally, this module defines the RequestValidator interface which provides a very early hook into the
    request processing (useful for global ratelimiting, DDoS prevention or access control).
"""


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


class BrowseHandler():  # webapp.RequestHandler
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

    def __init__(self, request: webob.Request, response: webob.Response):
        super()
        self.startTime = time.time()
        self.request = request
        self.response = response
        self.maxLogLevel = logging.DEBUG
        self._traceID = request.headers.get('X-Cloud-Trace-Context', "").split("/")[0] or utils.generateRandomString()
        self.is_deferred = False
        self.path_list = ()
        db.currentDbAccessLog.set(set())

    @property
    def isDevServer(self) -> bool:
        import warnings
        msg = "Use of `isDevServer` is deprecated; Use `conf[\"viur.instance.is_dev_server\"]` instead!"
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        logging.warning(msg)
        return conf["viur.instance.is_dev_server"]

    def selectLanguage(self, path: str) -> str:
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

    def processRequest(self) -> None:
        """
            Bring up the enviroment for this request, start processing and handle errors
        """
        # Check if it's a HTTP-Method we support
        reqestMethod = self.request.method.lower()
        if reqestMethod not in ["get", "post", "head"]:
            logging.error("Not supported")
            return
        self.isPostRequest = reqestMethod == "post"

        # Configure some basic parameters for this request
        self.internalRequest = False
        self.isSSLConnection = self.request.host_url.lower().startswith("https://")  # We have an encrypted channel
        if self.request.headers.get("X-AppEngine-TaskName", None) is not None:  # Check if we run in the appengine
            if self.request.environ.get("HTTP_X_APPENGINE_USER_IP") in _appengineServiceIPs:
                self.is_deferred = True
            elif os.getenv("TASKS_EMULATOR") is not None:
                self.is_deferred = True
        current.language.set(conf["viur.defaultLanguage"])
        self.disableCache = False  # Shall this request bypass the caches?
        self.args = []
        self.kwargs = {}
        # Check if we should process or abort the request
        for validator, reqValidatorResult in [(x, x.validate(self)) for x in self.requestValidators]:
            if reqValidatorResult is not None:
                logging.warning("Request rejected by validator %s" % validator.name)
                statusCode, statusStr, statusDescr = reqValidatorResult
                self.response.status = '%d %s' % (statusCode, statusStr)
                self.response.write(statusDescr)
                return
        path = self.request.path
        if conf["viur.instance.is_dev_server"]:
            # We'll have to emulate the task-queue locally as far as possible until supported by dev_appserver again
            self.pendingTasks = []

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

            path = self.selectLanguage(path)[1:]
            if conf["viur.requestPreprocessor"]:
                path = conf["viur.requestPreprocessor"](path)

            self.findAndCall(path)

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
                logging.info("Running task directly after request: %s" % str(task))
                task()

    def processTypeHint(self, typeHint: typing.ClassVar, inValue: typing.Union[str, typing.List[str]],
                        parsingOnly: bool) -> typing.Tuple[typing.Union[str, typing.List[str]], typing.Any]:
        """
            Helper function to enforce/convert the incoming :param: inValue to the type defined in :param: typeHint.
            Returns a string 2-tuple of the new value we'll store in self.kwargs as well as the parsed value that's
            passed to the caller. The first value is always the unmodified string, the unmodified list of strings or
            (in case typeHint is List[T] and the provided inValue is a simple string) a List containing only inValue.
            The second returned value is inValue converted to whatever type is suggested by typeHint.

            .. Warning: ViUR traditionally supports two ways to supply data to exposed functions: As *args (via
                Path components in the URL) and **kwargs (using POST or appending ?name=value parameters to the URL).
                When using a typeHint List[T], that parameter can only be submitted as a keyword argument. Trying to
                fill that parameter using a *args parameter will raise TypeError.

            ..  code-block:: python

                # Example:
                # Giving the following function, it's possible to fill *a* either by /test/aaa or by /test?a=aaa
                @exposed
                def test(a: str)

                # In case of
                @exposed
                def test(a: List[str])
                # only /test?a=aaa is valid. Invocations like /test/aaa will be rejected

            :param typeHint: Type to which inValue should be converted to
            :param inValue: The value that should be converted to the given type
            :param parsingOnly: If true, the parameter is a keyword argument which we can convert to List
            :return: 2-tuple of the original string-value and the converted value
        """
        try:
            typeOrigin = typeHint.__origin__  # Was: typing.get_origin(typeHint) (not supported in python 3.7)
        except:
            typeOrigin = None
        if typeOrigin is typing.Union:
            typeArgs = typeHint.__args__  # Was: typing.get_args(typeHint) (not supported in python 3.7)
            if len(typeArgs) == 2 and isinstance(None, typeArgs[1]):  # is None:
                return self.processTypeHint(typeArgs[0], inValue, parsingOnly)
        elif typeOrigin is list:
            if parsingOnly:
                raise TypeError("Cannot convert *args argument to list")
            typeArgs = typeHint.__args__  # Was: typing.get_args(typeHint) (not supported in python 3.7)
            if len(typeArgs) != 1:
                raise TypeError("Invalid List subtype")
            typeArgs = typeArgs[0]
            if not isinstance(inValue, list):
                inValue = [inValue]  # Force to List
            strRes = []
            parsedRes = []
            for elem in inValue:
                a, b = self.processTypeHint(typeArgs, elem, parsingOnly)
                strRes.append(a)
                parsedRes.append(b)
            if len(strRes) == 1:
                strRes = strRes[0]
            return strRes, parsedRes
        elif typeHint is str:
            if not isinstance(inValue, str):
                raise TypeError("Input argument to str typehint is not a string (probably a list)")
            return inValue, inValue
        elif typeHint is int:
            if not isinstance(inValue, str):
                raise TypeError("Input argument to int typehint is not a string (probably a list)")
            if not inValue.replace("-", "", 1).isdigit():
                raise TypeError("Failed to parse an integer typehint")
            i = int(inValue)
            return str(i), i
        elif typeHint is float:
            if not isinstance(inValue, str):
                raise TypeError("Input argument to float typehint is not a string (probably a list)")
            if not inValue.replace("-", "", 1).replace(",", ".", 1).replace(".", "", 1).isdigit():
                raise TypeError("Failed to parse an float typehint")
            f = float(inValue)
            if f != f:
                raise TypeError("Parsed float is a NaN-Value")
            return str(f), f
        elif typeHint is bool:
            if not isinstance(inValue, str):
                raise TypeError(f"Input argument to boolean typehint is not a str, but f{type(inValue)}")

            if inValue.strip().lower() in conf["viur.bone.boolean.str2true"]:
                return "True", True

            return "False", False

        elif typeOrigin is typing.Literal:
            inValueStr = str(inValue)
            for literal in typeHint.__args__:
                if inValueStr == str(literal):
                    return inValue, literal
            raise TypeError("Input argument must be one of these Literals: "
                            + ", ".join(map(repr, typeHint.__args__)))

        raise ValueError("TypeHint %s not supported" % typeHint)

    def findAndCall(self, path: str, *args, **kwargs) -> None:
        """
            Does the actual work of sanitizing the parameter, determine which @exposed (or @internalExposed) function
            to call (and with witch parameters)
        """

        # Parse the URL
        if path := parse.urlparse(path).path:
            self.path_list = tuple(unicodedata.normalize("NFC", parse.unquote(part))
                                   for part in path.strip("/").split("/"))

        # Prevent Hash-collision attacks
        kwargs = {}

        if len(self.request.params) > conf["viur.maxPostParamsCount"]:
            raise errors.BadRequest(
                f"Too many arguments supplied, exceeding maximum"
                f" of {conf['viur.maxPostParamsCount']} allowed arguments per request"
            )

        for key, value in self.request.params.items():
            try:
                key = unicodedata.normalize("NFC", key)
                value = unicodedata.normalize("NFC", value)
            except UnicodeError:
                # We received invalid unicode data (usually happens when
                # someone tries to exploit unicode normalisation bugs)
                raise errors.BadRequest()

            if key.startswith("_"):  # Ignore keys starting with _ (like VI's _unused_time_stamp)
                continue

            if key in kwargs:
                if isinstance(kwargs[key], list):
                    kwargs[key].append(value)
                else:  # Convert that key to a list
                    kwargs[key] = [kwargs[key], value]
            else:
                kwargs[key] = value

        if "self" in kwargs or "return" in kwargs:  # self or return is reserved for bound methods
            raise errors.BadRequest()

        caller = conf["viur.mainResolver"]
        idx = 0  # Count how may items from *args we'd have consumed (so the rest can go into *args of the called func
        path_found = True
        for part in self.path_list:
            if "canAccess" in caller and not caller["canAccess"]():
                # We have a canAccess function guarding that object,
                # and it returns False...
                raise errors.Unauthorized()
            idx += 1
            part = part.replace("-", "_").replace(".", "_")
            if part not in caller:
                part = "index"

            if part in caller:
                caller = caller[part]
                if (("exposed" in dir(caller) and caller.exposed) or
                        ("internalExposed" in dir(caller) and caller.internalExposed and self.internalRequest)) and \
                        hasattr(caller, '__call__'):
                    if part == "index":
                        idx -= 1
                    args = self.path_list[idx:] + args  # Prepend the rest of Path to args
                    break

                elif part == "index":
                    path_found = False
                    break

            else:
                path_found = False
                break

        if not path_found:
            from viur.core import utils
            raise errors.NotFound(
                f"""The path {utils.escapeString("/".join(self.path_list[:idx]))} could not be found""")

        if (not callable(caller) or ((not "exposed" in dir(caller) or not caller.exposed)) and (
            not "internalExposed" in dir(caller) or not caller.internalExposed or not self.internalRequest)):
            if "index" in caller \
                and (callable(caller["index"]) \
                     and ("exposed" in dir(caller["index"]) and caller["index"].exposed) \
                     or ("internalExposed" in dir(
                    caller["index"]) and caller["index"].internalExposed and self.internalRequest)):
                caller = caller["index"]
            else:
                raise errors.MethodNotAllowed()
        # Check for forceSSL flag
        if not self.internalRequest \
                and "forceSSL" in dir(caller) \
                and caller.forceSSL \
                and not self.request.host_url.lower().startswith("https://") \
                and not conf["viur.instance.is_dev_server"]:
            raise (errors.PreconditionFailed("You must use SSL to access this ressource!"))
        # Check for forcePost flag
        if "forcePost" in dir(caller) and caller.forcePost and not self.isPostRequest:
            raise (errors.MethodNotAllowed("You must use POST to access this ressource!"))
        self.args = args
        self.kwargs = kwargs
        # Check if this request should bypass the caches
        if self.request.headers.get("X-Viur-Disable-Cache"):
            from viur.core import utils
            # No cache requested, check if the current user is allowed to do so
            if (user := current.user.get()) and "root" in user["access"]:
                logging.debug("Caching disabled by X-Viur-Disable-Cache header")
                self.disableCache = True
        try:
            annotations = typing.get_type_hints(caller)
            if annotations and not self.internalRequest:
                newKwargs = {}  # The dict of new **kwargs we'll pass to the caller
                newArgs = []  # List of new *args we'll pass to the caller

                # FIXME: Use inspect.signature() for all this stuff...
                argsOrder = caller.__code__.co_varnames[:caller.__code__.co_argcount]
                # In case of a method, ignore the 'self' parameter
                if inspect.ismethod(caller):
                    argsOrder = argsOrder[1:]

                # Map args in
                for idx in range(0, min(len(self.args), len(argsOrder))):
                    paramKey = argsOrder[idx]
                    if paramKey in annotations:  # We have to enforce a type-annotation for this *args parameter
                        _, newTypeValue = self.processTypeHint(annotations[paramKey], self.args[idx], True)
                        newArgs.append(newTypeValue)
                    else:
                        newArgs.append(self.args[idx])
                newArgs.extend(self.args[min(len(self.args), len(argsOrder)):])
                # Last, we map the kwargs in
                for k, v in kwargs.items():
                    if k in annotations:
                        newStrValue, newTypeValue = self.processTypeHint(annotations[k], v, False)
                        self.kwargs[k] = newStrValue
                        newKwargs[k] = newTypeValue
                    else:
                        newKwargs[k] = v
            else:
                newArgs = self.args
                newKwargs = self.kwargs
            if (conf["viur.debug.traceExternalCallRouting"] and not self.internalRequest) or conf[
                "viur.debug.traceInternalCallRouting"]:
                logging.debug("Calling %s with args=%s and kwargs=%s" % (str(caller), str(newArgs), str(newKwargs)))
            res = caller(*newArgs, **newKwargs)
            res = str(res).encode("UTF-8") if not isinstance(res, bytes) else res
            self.response.write(res)
        except TypeError as e:
            if self.internalRequest:  # We provide that "service" only for requests originating from outside
                raise
            if "viur/core/request.py\", line 5" in traceback.format_exc().splitlines()[-3]:
                # Don't raise NotAcceptable for type-errors raised deep somewhere inside caller.
                # We check if the last line in traceback originates from viur/core/request.py and a line starting with
                # 5 and only raise NotAcceptable then. Otherwise a "normal" 500 Server error will be raised.
                # This is kinda hackish, however this is much faster than reevaluating the args and kwargs passed
                # to caller as we did in ViUR2.
                raise errors.NotAcceptable()
            raise

    def saveSession(self) -> None:
        current.session.get().save(self)


from .i18n import translate  # noqa: E402
