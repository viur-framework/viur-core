from contextvars import ContextVar

request = ContextVar("Request", default=None)
request_data = ContextVar("Request-Data", default=None)
session = ContextVar("Session", default=None)
language = ContextVar("Language", default=None)
user = ContextVar("User", default=None)

class CurrentUser:
    def __init__(self):
        print("in init")
    def __repr__(self):
        from viur.core import conf  # noqa: E402 # import works only here because circular imports
        if user_mod := getattr(conf["viur.mainApp"], "user", None):
            user.set(user_mod.getCurrentUser())
            print("user")
            print(type(user.get()))
            return user.get()
    def __str__(self):
        return str(self.__repr__())
    def __new__(cls):
        print("in new")
        print(f'Creating a new {cls.__name__} object...')
        obj = object.__new__(cls)
        return obj

user.set(CurrentUser())
