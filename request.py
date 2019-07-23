# -*- coding: utf-8 -*-
import threading
import sys, traceback, os, inspect
from server.config import conf
from urllib import parse
from string import Template
from io import StringIO
import webob
from server import session, errors
from urllib.parse import urljoin
from server import utils
import logging
import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud.logging.resource import Resource
from time import time

translations = None

client = google.cloud.logging.Client()
loggingRessource = Resource(type="gae_app",
							labels={
								"project_id": utils.projectID,
								"module_id": "default",
							})

reqLogger = client.logger("ViUR")


class ViURDefaultLogger(CloudLoggingHandler):
	def emit(self, record):
		message = super(ViURDefaultLogger, self).format(record)
		try:
			currentReq = current.get()
			TRACE = "projects/{}/traces/{}".format(client.project, currentReq._traceID)
			currentReq.maxLogLevel = max(currentReq.maxLogLevel, record.levelno)
		except:
			TRACE = None
		self.transport.send(
			record,
			message,
			resource=self.resource,
			labels=self.labels,
			trace=TRACE
		)


handler = ViURDefaultLogger(client, name="ViUR-Messages", resource=Resource(type="gae_app", labels={}))
google.cloud.logging.handlers.setup_logging(handler)
logging.getLogger().setLevel(logging.DEBUG)


class BrowseHandler():  # webapp.RequestHandler
	"""
		This class accepts the requests, collect its parameters and routes the request
		to its destination function.

		:warning: Don't instantiate! Don't subclass! DON'T TOUCH! ;)
	"""

	# COPY START

	def redirect(self, uri, permanent=False, abort=False, code=None, body=None,
				 request=None, response=None):
		"""Issues an HTTP redirect to the given relative URI.

		This won't stop code execution unless **abort** is True. A common
		practice is to return when calling this method::

			return redirect('/some-path')

		:param uri:
			A relative or absolute URI (e.g., ``'../flowers.html'``).
		:param permanent:
			If True, uses a 301 redirect instead of a 302 redirect.
		:param abort:
			If True, raises an exception to perform the redirect.
		:param code:
			The redirect status code. Supported codes are 301, 302, 303, 305,
			and 307.  300 is not supported because it's not a real redirect
			and 304 because it's the answer for a request with defined
			``If-Modified-Since`` headers.
		:param body:
			Response body, if any.
		:param request:
			Optional request object. If not set, uses :func:`get_request`.
		:param response:
			Optional response object. If not set, a new response is created.
		:returns:
			A :class:`Response` instance.
		"""
		request = self.request
		response = self.response
		if uri.startswith(('.', '/')):
			uri = str(urljoin(request.url, uri))

		if code is None:
			if permanent:
				code = 301
			else:
				code = 302

		assert code in (301, 302, 303, 305, 307), \
			'Invalid redirect status code.'

		if abort:
			headers = response.headers.copy() if response is not None else []
			headers['Location'] = uri
			_abort(code, headers=headers)

		response.headers['Location'] = uri
		response.status = code
		if body is not None:
			response.write(body)

		return response

	# COPY END

	def __init__(self, request: webob.Request, response: webob.Response):
		super()
		self.startTime = time()
		self.request = request
		self.response = response
		self.maxLogLevel = logging.DEBUG
		self._traceID = request.headers.get('X-Cloud-Trace-Context') or utils.generateRandomString()

	def selectLanguage(self, path: str):
		"""
			Tries to select the best language for the current request.
		"""
		if translations is None:
			# This project doesn't use the multi-language feature, nothing to do here
			return (path)
		if conf["viur.languageMethod"] == "session":
			# We store the language inside the session, try to load it from there
			if not session.current.getLanguage():
				if "X-Appengine-Country" in self.request.headers:
					lng = self.request.headers["X-Appengine-Country"].lower()
					if lng in conf["viur.availableLanguages"] + list(conf["viur.languageAliasMap"].keys()):
						session.current.setLanguage(lng)
						self.language = lng
					else:
						session.current.setLanguage(conf["viur.defaultLanguage"])
			else:
				self.language = session.current.getLanguage()
		elif conf["viur.languageMethod"] == "domain":
			host = self.request.host_url.lower()
			host = host[host.find("://") + 3:].strip(" /")  # strip http(s)://
			if host.startswith("www."):
				host = host[4:]
			if host in conf["viur.domainLanguageMapping"]:
				self.language = conf["viur.domainLanguageMapping"][host]
			else:  # We have no language configured for this domain, try to read it from session
				if session.current.getLanguage():
					self.language = session.current.getLanguage()
		elif conf["viur.languageMethod"] == "url":
			tmppath = urlparse.urlparse(path).path
			tmppath = [urlparse.unquote(x) for x in tmppath.lower().strip("/").split("/")]
			if len(tmppath) > 0 and tmppath[0] in conf["viur.availableLanguages"] + list(
					conf["viur.languageAliasMap"].keys()):
				self.language = tmppath[0]
				return (path[len(tmppath[0]) + 1:])  # Return the path stripped by its language segment
			else:  # This URL doesnt contain an language prefix, try to read it from session
				if session.current.getLanguage():
					self.language = session.current.getLanguage()
				elif "X-Appengine-Country" in self.request.headers.keys():
					lng = self.request.headers["X-Appengine-Country"].lower()
					if lng in conf["viur.availableLanguages"] or lng in conf["viur.languageAliasMap"]:
						self.language = lng
		return (path)

	def processRequest(self):
		"""
			Bring up the enviroment for this request, start processing and handle errors
		"""
		# with conf["viur.tracer"].span(name="request."):
		# Check if it's a HTTP-Method we support
		reqestMethod = self.request.method.lower()
		if reqestMethod not in ["get", "post", "head"]:
			logging.error("Not supported")
			return
		self.isPostRequest = reqestMethod == "post"

		# Configure some basic parameters for this request
		self.internalRequest = False
		self.isDevServer = os.environ['GAE_ENV'] == "localdev"  # Were running on development Server
		self.isSSLConnection = self.request.host_url.lower().startswith("https://")  # We have an encrypted channel
		self.language = conf["viur.defaultLanguage"]
		self.disableCache = False  # Shall this request bypass the caches?
		self.args = []
		self.kwargs = {}
		path = self.request.path

		# Add CSP headers early (if any)
		if conf["viur.security.contentSecurityPolicy"] and conf["viur.security.contentSecurityPolicy"]["_headerCache"]:
			for k, v in conf["viur.security.contentSecurityPolicy"]["_headerCache"].items():
				self.response.headers[k] = v
		if self.isSSLConnection:  # Check for HTST and PKP headers only if we have a secure channel.
			if conf["viur.security.strictTransportSecurity"]:
				self.response.headers["Strict-Transport-Security"] = conf["viur.security.strictTransportSecurity"]
			if conf["viur.security.publicKeyPins"]:
				self.response.headers["Public-Key-Pins"] = conf["viur.security.publicKeyPins"]

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

		# Ensure that TLS is used if required
		if conf["viur.forceSSL"] and not self.isSSLConnection and not self.isDevServer:
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
				self.redirect("https://%s/" % host)
				return
		if path[:10] == "/_viur/dlf":
			self.response.write("okay")
			return
		try:
			session.current.load(self)  # self.request.cookies )
			path = self.selectLanguage(path)
			if conf["viur.requestPreprocessor"]:
				path = conf["viur.requestPreprocessor"](path)
			self.findAndCall(path)
		except errors.Redirect as e:
			if conf["viur.debug.traceExceptions"]:
				raise
			try:
				self.redirect(e.url)
			except Exception as e:
				logging.exception(e)
				raise
		except errors.HTTPException as e:
			if conf["viur.debug.traceExceptions"]:
				raise
			self.response.body = b""
			self.response.status = '%d %s' % (e.status, e.descr)
			res = None
			if conf["viur.errorHandler"]:
				try:
					res = conf["viur.errorHandler"](e)
				except Exception as newE:
					logging.error("viur.errorHandler failed!")
					logging.exception(newE)
					res = None
			if not res:
				tpl = Template(open(conf["viur.errorTemplate"], "r").read())
				res = tpl.safe_substitute({"error_code": e.status, "error_name": e.name, "error_descr": e.descr})
			self.response.write(res.encode("UTF-8"))
		except Exception as e:  # Something got really wrong
			logging.error("Viur caught an unhandled exception!")
			logging.exception(e)
			self.response.body = b""
			self.response.status = 500
			res = None
			if conf["viur.errorHandler"]:
				try:
					res = conf["viur.errorHandler"](e)
				except Exception as newE:
					logging.error("viur.errorHandler failed!")
					logging.exception(newE)
					res = None
			if not res:
				tpl = Template(open(conf["viur.errorTemplate"], "r").read())
				descr = "The server encountered an unexpected error and is unable to process your request."
				if self.isDevServer:  # Were running on development Server
					strIO = StringIO()
					traceback.print_exc(file=strIO)
					descr = strIO.getvalue()
					descr = descr.replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;").replace("\n",
																										   "<br />")
				res = tpl.safe_substitute(
					{"error_code": "500", "error_name": "Internal Server Error", "error_descr": descr})
			self.response.write(res.encode("UTF-8"))
		finally:
			self.saveSession()

			SEVERITY = "DEBUG"
			if self.maxLogLevel >= 50:
				SEVERITY = "CRITICAL"
			elif self.maxLogLevel >= 40:
				SEVERITY = "ERROR"
			elif self.maxLogLevel >= 30:
				SEVERITY = "WARNING"
			elif self.maxLogLevel >= 20:
				SEVERITY = "INFO"

			TRACE = "projects/{}/traces/{}".format(client.project, self._traceID)

			REQUEST = {
				'requestMethod': self.request.method,
				'requestUrl': self.request.url,
				'status': self.response.status_code,
				'userAgent': self.request.headers.get('USER-AGENT'),
				'responseSize': self.response.content_length,
				'latency': "%0.3fs" % (time() - self.startTime),
				'remoteIp': self.request.environ.get("HTTP_X_APPENGINE_USER_IP")
			}
			reqLogger.log_text("", client=client, severity=SEVERITY, http_request=REQUEST, trace=TRACE,
							   resource=loggingRessource)

	def findAndCall(self, path, *args, **kwargs):  # Do the actual work: process the request
		# Prevent Hash-collision attacks
		kwargs = {}
		stopCount = conf["viur.maxPostParamsCount"]
		for key, value in self.request.params.iteritems():
			if key in kwargs:
				if isinstance(kwargs[key], list):
					kwargs[key].append(value)
				else:
					kwargs[key] = [kwargs[key], value]
			else:
				kwargs[key] = value
			stopCount -= 1
			if not stopCount:  # We reached zero; maximum PostParamsCount excceded
				raise errors.NotAcceptable()

		if "self" in kwargs:  # self is reserved for bound methods
			raise errors.BadRequest()
		# Parse the URL
		path = parse.urlparse(path).path
		self.pathlist = [parse.unquote(x) for x in path.strip("/").split("/")]
		caller = conf["viur.mainApp"]
		idx = 0  # Count how may items from *args we'd have consumed (so the rest can go into *args of the called func
		for currpath in self.pathlist:
			if "canAccess" in dir(caller) and not caller.canAccess():
				# We have a canAccess function guarding that object,
				# and it returns False...
				raise (errors.Unauthorized())
			idx += 1
			currpath = currpath.replace("-", "_").replace(".", "_")
			if currpath in dir(caller):
				caller = getattr(caller, currpath)
				if (("exposed" in dir(caller) and caller.exposed) or ("internalExposed" in dir(
						caller) and caller.internalExposed and self.internalRequest)) and hasattr(caller, '__call__'):
					args = self.pathlist[idx:] + [x for x in args]  # Prepend the rest of Path to args
					break
			elif "index" in dir(caller):
				caller = getattr(caller, "index")
				if (("exposed" in dir(caller) and caller.exposed) or ("internalExposed" in dir(
						caller) and caller.internalExposed and self.internalRequest)) and hasattr(caller, '__call__'):
					args = self.pathlist[idx - 1:] + [x for x in args]
					break
				else:
					raise (errors.NotFound("The path %s could not be found" % "/".join(
						[("".join([y for y in x if y.lower() in "0123456789abcdefghijklmnopqrstuvwxyz"])) for x in
						 self.pathlist[: idx]])))
			else:
				raise (errors.NotFound("The path %s could not be found" % "/".join(
					[("".join([y for y in x if y.lower() in "0123456789abcdefghijklmnopqrstuvwxyz"])) for x in
					 self.pathlist[: idx]])))
		if (not callable(caller) or ((not "exposed" in dir(caller) or not caller.exposed)) and (
				not "internalExposed" in dir(caller) or not caller.internalExposed or not self.internalRequest)):
			if "index" in dir(caller) \
					and (callable(caller.index) \
						 and ("exposed" in dir(caller.index) and caller.index.exposed) \
						 or ("internalExposed" in dir(
						caller.index) and caller.index.internalExposed and self.internalRequest)):
				caller = caller.index
			else:
				raise (errors.MethodNotAllowed())
		# Check for forceSSL flag
		if not self.internalRequest \
				and "forceSSL" in dir(caller) \
				and caller.forceSSL \
				and not self.request.host_url.lower().startswith("https://") \
				and not self.isDevServer:
			raise (errors.PreconditionFailed("You must use SSL to access this ressource!"))
		# Check for forcePost flag
		if "forcePost" in dir(caller) and caller.forcePost and not self.isPostRequest:
			raise (errors.MethodNotAllowed("You must use POST to access this ressource!"))
		self.args = []
		for arg in args:
			if isinstance(arg, str):
				self.args.append(arg)
			else:
				try:
					self.args.append(arg.decode("UTF-8"))
				except:
					pass
		self.kwargs = kwargs
		# Check if this request should bypass the caches
		if self.request.headers.get("X-Viur-Disable-Cache"):
			from server import utils
			# No cache requested, check if the current user is allowed to do so
			user = utils.getCurrentUser()
			if user and "root" in user["access"]:
				logging.debug("Caching disabled by X-Viur-Disable-Cache header")
				self.disableCache = True
		try:
			if (conf["viur.debug.traceExternalCallRouting"] and not self.internalRequest) or conf[
				"viur.debug.traceInternalCallRouting"]:
				logging.debug("Calling %s with args=%s and kwargs=%s" % (str(caller), str(args), str(kwargs)))
			res = caller(*self.args, **self.kwargs)
			res = str(res).encode("UTF-8") if not isinstance(res, bytes) else res
			self.response.write(res)
		except TypeError as e:
			if self.internalRequest:  # We provide that "service" only for requests originating from outside
				raise
			# Check if the function got too few arguments and raise a NotAcceptable error
			tmpRes = {}
			argsOrder = list(caller.__code__.co_varnames)[1: caller.__code__.co_argcount]
			# Map default values in
			reversedArgsOrder = argsOrder[:: -1]
			for defaultValue in list(caller.__defaults__ or [])[:: -1]:
				tmpRes[reversedArgsOrder.pop(0)] = defaultValue
			del reversedArgsOrder
			# Map args in
			setArgs = []  # Store a list of args already set by *args
			for idx in range(0, min(len(args), len(argsOrder))):
				setArgs.append(argsOrder[idx])
				tmpRes[argsOrder[idx]] = args[idx]
			# Last, we map the kwargs in
			for k, v in kwargs.items():
				if k in setArgs:  # This key has already been set by *args
					raise (errors.NotAcceptable())  # We reraise that exception as we got duplicate arguments
				tmpRes[k] = v
			# Last check, that every parameter is satisfied:
			if not all([x in tmpRes.keys() for x in argsOrder]):
				raise (errors.NotAcceptable())
			raise

	def saveSession(self):
		session.current.save(self)


class RequestWrapper(object):
	"""
		Request Wrapper.
		Allows applications to access the current request
		object (google.appengine.ext.webapp.Request)
		without having a direct reference to it.
		Use singleton 'current' instead of this class.

		Example::

			from request import current as currentRequest
			currentRequest.get().headers
	"""

	def __init__(self, *args, **kwargs):
		super(RequestWrapper, self).__init__(*args, **kwargs)
		self.data = threading.local()

	def setRequest(self, request):
		self.data.request = request
		self.data.reqData = {}

	def get(self):
		return (self.data.request)

	def requestData(self):
		return (self.data.reqData)


current = RequestWrapper()
