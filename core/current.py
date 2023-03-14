from contextvars import ContextVar

request = ContextVar("Request", default=None)
request_data = ContextVar("Request-Data", default=None)
session = ContextVar("Session", default=None)
language = ContextVar("Language", default=None)
user = None


class CurrentUser:
    def get(self, default=None):
        from viur.core import conf  # noqa: E402 # import works only here because circular imports
        if user_mod := getattr(conf["viur.mainApp"], "user", None):
            global user
            user = ContextVar("User", default=None)
            user.set(user_mod.getCurrentUser())
            return user.get(default)

    def set(self, *args, **kwargs):
        pass
