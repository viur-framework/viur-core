class HTTPException(Exception):
    """
        Base-Class for all Exceptions that should match to an http error-code
    """

    def __init__(self, status: int, name: str, descr: str):
        """
        :param status: The desired http error-code (404, 500, ...)
        :param name: Name as of RFC 2616
        :param descr: Human-readable description of that error
        """
        super(HTTPException, self).__init__()
        self.status = status

        from .i18n import translate  # fixme: This might be done better
        self.name = name
        self.descr = str(translate(descr))

    def process(self):
        pass


class BadRequest(HTTPException):
    """
        BadRequest
    """

    def __init__(self, descr: str = "The request your browser sent cannot be fulfilled due to bad syntax."):
        super(BadRequest, self).__init__(status=400, name="Bad Request", descr=descr)


class Redirect(HTTPException):
    """
        Causes an 303 - See Other (or 302 - Found if requested / 301 - Moved Permanently) redirect
    """

    def __init__(self, url: str, descr: str = "Redirect", status: int = 303):
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

    def __init__(self, descr: str = "The resource is protected and you don't have the permissions."):
        super(Unauthorized, self).__init__(status=401, name="Unauthorized", descr=descr)


class PaymentRequired(HTTPException):
    """
        PaymentRequired

        Not used inside viur.core. This status-code is reserved for further use and is currently not
        supported by clients.
    """

    def __init__(self, descr: str = "Payment Required"):
        super(PaymentRequired, self).__init__(status=402, name="Payment Required", descr=descr)


class Forbidden(HTTPException):
    """
        Forbidden

        Not used inside viur.core. May be utilized in the future to distinguish between requests from
        guests and users, who are logged in but don't have the permission.
    """

    def __init__(self, descr: str = "The resource is protected and you don't have the permissions."):
        super(Forbidden, self).__init__(status=403, name="Forbidden", descr=descr)


class NotFound(HTTPException):
    """
        NotFound

        Usually raised in view() methods from application if the given key is invalid.
    """

    def __init__(self, descr: str = "The requested resource could not be found."):
        super(NotFound, self).__init__(status=404, name="Not Found", descr=descr)


class MethodNotAllowed(HTTPException):
    """
        MethodNotAllowed

        Raised if a function is accessed which doesn't have the @exposed / @internalExposed decorator or
        if the request arrived using get, but the function has the @forcePost flag.
    """

    def __init__(self, descr: str = "Method Not Allowed"):
        super(MethodNotAllowed, self).__init__(status=405, name="Method Not Allowed", descr=descr)


class NotAcceptable(HTTPException):
    """
        NotAcceptable

        Signals that the parameters supplied doesn't match the function signature
    """

    def __init__(self, descr: str = "The request cannot be processed due to missing or invalid parameters."):
        super(NotAcceptable, self).__init__(status=406, name="Not Acceptable", descr=descr)


class RequestTimeout(HTTPException):
    """
        RequestTimeout

        This must be used for the task api to indicate it should retry
    """

    def __init__(self, descr: str = "The request has timed out."):
        super(RequestTimeout, self).__init__(status=408, name="Request Timeout", descr=descr)


class Gone(HTTPException):
    """
        Gone

        Not used inside viur.core
    """

    def __init__(self, descr: str = "Gone"):
        super(Gone, self).__init__(status=410, name="Gone", descr=descr)


class PreconditionFailed(HTTPException):
    """
        PreconditionFailed

        Mostly caused by a missing/invalid securitykey.
    """

    def __init__(self, descr: str = "Precondition Failed"):
        super(PreconditionFailed, self).__init__(status=412, name="Precondition Failed", descr=descr)


class RequestTooLarge(HTTPException):
    """
        RequestTooLarge

        Not used inside viur.core
    """

    def __init__(self, descr: str = "Request Too Large"):
        super(RequestTooLarge, self).__init__(status=413, name="Request Too Large", descr=descr)


class Locked(HTTPException):
    """
        Locked

        Raised if a resource cannot be deleted due to incomming relational locks
    """

    def __init__(self, descr: str = "Ressource is Locked"):
        super(Locked, self).__init__(status=423, name="Ressource is Locked", descr=descr)


class TooManyRequests(HTTPException):
    """
        Too Many Requests

        The 429 status code indicates that the user has sent too many
        requests in a given amount of time ("rate limiting").
    """

    def __init__(self, descr: str = "Too Many Requests"):
        super(TooManyRequests, self).__init__(status=429, name="Too Many Requests", descr=descr)


class Censored(HTTPException):
    """
        Censored

        Not used inside viur.core
    """

    def __init__(self, descr: str = "Unavailable For Legal Reasons"):
        super(Censored, self).__init__(status=451, name="Unavailable For Legal Reasons", descr=descr)


class InternalServerError(HTTPException):
    """
        InternalServerError

        The catch-all error raised by the server if your code raises any python-exception not deriving from
        HTTPException
    """

    def __init__(self, descr: str = "Internal Server Error"):
        super(InternalServerError, self).__init__(status=500, name="Internal Server Error", descr=descr)


class NotImplemented(HTTPException):
    """
        NotImplemented

        Not really implemented at the moment :)
    """

    def __init__(self, descr: str = "Not Implemented"):
        super(NotImplemented, self).__init__(status=501, name="Not Implemented", descr=descr)


class BadGateway(HTTPException):
    """
        BadGateway

        Not used inside viur.core
    """

    def __init__(self, descr: str = "Bad Gateway"):
        super(BadGateway, self).__init__(status=502, name="Bad Gateway", descr=descr)


class ServiceUnavailable(HTTPException):
    """
        ServiceUnavailable

        Not used inside viur.core
    """

    def __init__(self, descr: str = "Service Unavailable"):
        super(ServiceUnavailable, self).__init__(status=503, name="Service Unavailable", descr=descr)
