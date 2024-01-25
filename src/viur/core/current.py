from contextvars import ContextVar
import typing as t

if t.TYPE_CHECKING:
    from .request import Router
    from .session import Session
    from .skeleton import SkeletonInstance

request: ContextVar[t.Optional["Router"]] = ContextVar("Request", default=None)
request_data: ContextVar[t.Optional[dict]] = ContextVar("Request-Data", default=None)
session: ContextVar[t.Optional["Session"]] = ContextVar("Session", default=None)
language: ContextVar[t.Optional[str]] = ContextVar("Language", default=None)
user: ContextVar[t.Optional["SkeletonInstance"]] = ContextVar("User", default=None)
