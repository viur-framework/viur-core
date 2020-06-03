# -*- coding: utf-8 -*-

class HTTPException(Exception):
	"""
		Base-Class for all Exceptions that should match to an http error-code
	"""

	def __init__(self, status, name, descr):
		"""

		:param status: The desired http error-code (404, 500, ...)
		:type status: int
		:param name: Name as of RFC 2616
		:type name: str
		:param descr: Human-readable description of that error
		:type descr: str

		"""
		super(HTTPException, self).__init__()
		self.status = status
		self.name = name
		self.descr = descr

	def process(self):
		pass


class BadRequest(HTTPException):
	"""
		BadRequest

		Not used inside the server
	"""

	def __init__(self, descr="The request your browser sent cannot be fulfilled due to bad syntax."):
		super(BadRequest, self).__init__(status=400, name="Bad Request", descr=descr)


class Redirect(HTTPException):
	"""
		Causes an 303 - See Other (or 302 - Found if requested / 301 - Moved Permanently) redirect
	"""

	def __init__(self, url, descr="Redirect", status=303):
		if not isinstance(status, int) or status not in {301, 302, 303, 307, 308}:
			raise ValueError("Invalid status %r. Only the status codes 301, 302, 303, 307 and 308 "
							 "are valid for a redirect." % status)
		super(Redirect, self).__init__(status=status, name="Redirect", descr=descr)
		self.url = url


class Unauthorized(HTTPException):
	"""
		Unauthorized

		Raised whenever a request hits an path protected by canAccess() or a canAdd/canEdit/... -Function inside
		an application returns false.
	"""

	def __init__(self, descr="The resource is protected and you don't have the permissions."):
		super(Unauthorized, self).__init__(status=401, name="Unauthorized", descr=descr)


class PaymentRequired(HTTPException):
	"""
		PaymentRequired

		Not used inside the server. This status-code is reserved for further use and is currently not
		supported by clients.
	"""

	def __init__(self, descr="Payment Required"):
		super(PaymentRequired, self).__init__(status=402, name="Payment Required", descr=descr)


class Forbidden(HTTPException):
	"""
		Forbidden

		Not used inside the server. May be utilized in the future to distinguish between requests from
		guests and users, who are logged in but don't have the permission.
	"""

	def __init__(self, descr="The resource is protected and you don't have the permissions."):
		super(Forbidden, self).__init__(status=403, name="Forbidden", descr=descr)


class NotFound(HTTPException):
	"""
		NotFound

		Usually raised in view() methods from application if the given key is invalid.
	"""

	def __init__(self, descr="The requested resource could not be found."):
		super(NotFound, self).__init__(status=404, name="Not Found", descr=descr)


class MethodNotAllowed(HTTPException):
	"""
		MethodNotAllowed

		Raised if a function is accessed which doesn't have the @exposed / @internalExposed decorator or
		if the request arrived using get, but the function has the @forcePost flag.
	"""

	def __init__(self, descr="Method Not Allowed"):
		super(MethodNotAllowed, self).__init__(status=405, name="Method Not Allowed", descr=descr)


class NotAcceptable(HTTPException):
	"""
		NotAcceptable

		Signals that the parameters supplied doesn't match the function signature
	"""

	def __init__(self, descr="The request cannot be processed due to missing or invalid parameters."):
		super(NotAcceptable, self).__init__(status=406, name="Not Acceptable", descr=descr)


class RequestTimeout(HTTPException):
	"""
		RequestTimeout

		This must be used for the task api to indicate it should retry
	"""

	def __init__(self, descr="The request has timed out."):
		super(RequestTimeout, self).__init__(status=408, name="Request Timeout", descr=descr)


class Gone(HTTPException):
	"""
		Gone

		Not used inside the server
	"""

	def __init__(self, descr="Gone"):
		super(Gone, self).__init__(status=410, name="Gone", descr=descr)


class PreconditionFailed(HTTPException):
	"""
		PreconditionFailed

		Mostly caused by a missing/invalid securitykey.
	"""

	def __init__(self, descr="Precondition Failed"):
		super(PreconditionFailed, self).__init__(status=412, name="Precondition Failed", descr=descr)


class RequestTooLarge(HTTPException):
	"""
		RequestTooLarge

		Not used inside the server
	"""

	def __init__(self, descr="Request Too Large"):
		super(RequestTooLarge, self).__init__(status=413, name="Request Too Large", descr=descr)


class Locked(HTTPException):
	"""
		Locked

		Raised if a resource cannot be deleted due to incomming relational locks
	"""

	def __init__(self, descr="Ressource is Locked"):
		super(Locked, self).__init__(status=423, name="Ressource is Locked", descr=descr)


class Censored(HTTPException):
	"""
		Censored

		Not used inside the server
	"""

	def __init__(self, descr="Unavailable For Legal Reasons"):
		super(Censored, self).__init__(status=451, name="Unavailable For Legal Reasons", descr=descr)


class InternalServerError(HTTPException):
	"""
		InternalServerError

		The catch-all error raised by the server if your code raises any python-exception not deriving from
		HTTPException
	"""

	def __init__(self, descr="Internal Server Error"):
		super(InternalServerError, self).__init__(status=500, name="Internal Server Error", descr=descr)


class NotImplemented(HTTPException):
	"""
		NotImplemented

		Not really implemented at the moment :)
	"""

	def __init__(self, descr="Not Implemented"):
		super(NotImplemented, self).__init__(status=501, name="Not Implemented", descr=descr)


class BadGateway(HTTPException):
	"""
		BadGateway

		Not used
	"""

	def __init__(self, descr="Bad Gateway"):
		super(BadGateway, self).__init__(status=502, name="Bad Gateway", descr=descr)


class ServiceUnavailable(HTTPException):
	"""
		ServiceUnavailable

		Raised if the flag "viur.disabled" in conf.sharedConf is set
	"""

	def __init__(self, descr="Service Unavailable"):
		super(ServiceUnavailable, self).__init__(status=503, name="Service Unavailable", descr=descr)


class ReadFromClientError(object):
	"""
		ReadFromClientError

		Internal use only. Used as a **return-value** (its not raised!) to transport information on errors
		from fromClient in bones to the surrounding skeleton class
	"""

	def __init__(self, errors, forceFail=False):
		super(ReadFromClientError, self).__init__()
		self.errors = errors
		self.forceFail = forceFail


class ViurException(Exception):
	pass


class InvalidConfigException(ViurException):
	"""
		This exception is usually thrown if a config isn't set or is incorrect.
	"""
