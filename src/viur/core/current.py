from contextvars import ContextVar

request = ContextVar("Request", default=None)
request_data = ContextVar("Request-Data", default=None)
session = ContextVar("Session", default=None)
language = ContextVar("Language", default=None)
user = ContextVar("User", default=None)
