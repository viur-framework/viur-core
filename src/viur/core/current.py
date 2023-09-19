import typing
from contextvars import ContextVar
from typing import Optional

if typing.TYPE_CHECKING:
    from .request import Router
    from .session import Session
    from .skeleton import SkeletonInstance

request: ContextVar[Optional["Router"]] = ContextVar("Request", default=None)
request_data: ContextVar[Optional[dict]] = ContextVar("Request-Data", default=None)
session: ContextVar[Optional["Session"]] = ContextVar("Session", default=None)
language: ContextVar[Optional[str]] = ContextVar("Language", default=None)
user: ContextVar[Optional["SkeletonInstance"]] = ContextVar("User", default=None)
