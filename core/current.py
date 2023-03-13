from contextvars import ContextVar

request = ContextVar("Request", default=None)
request_data = ContextVar("Request-Data", default=None)
session = ContextVar("Session", default=None)
language = ContextVar("Language", default=None)
user = ContextVar("User", default=None)


class CurrentUser:
    def __init__(self):
        self.loaded = False
        self.value = None

    def __repr__(self):
        if self.loaded:
            return self.value
        self.loaded = True
        from viur.core import conf  # noqa: E402 # import works only here because circular imports
        if user_mod := getattr(conf["viur.mainApp"], "user", None):
            self.value = user_mod.getCurrentUser()
            return self.value

    def __str__(self):
        return str(self.__repr__())

user.set(CurrentUser())
