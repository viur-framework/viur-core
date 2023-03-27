from contextvars import ContextVar
from typing import Any, Iterable, Tuple

request = ContextVar("Request", default=None)
request_data = ContextVar("Request-Data", default=None)
session = ContextVar("Session", default=None)
language = ContextVar("Language", default=None)


class CurrentUserWrapper:

    def __init__(self):
        self.loaded = False
        self._data = None

    def load(self):
        if not self.loaded:
            from viur.core import conf  # noqa: E402 # import works only here because circular imports
            self.loaded = True
            if user_mod := getattr(conf["viur.mainApp"], "user", None):
                self._data = user_mod.getCurrentUser()

    def items(self, yieldBoneValues: bool = False) -> Iterable[Tuple[str, 'BaseBone']]:
        if yieldBoneValues:
            for key in self._data.keys():
                yield key, self[key]
        else:
            yield from self._data.items()

    def keys(self) -> Iterable[str]:
        yield from self._data.keys()

    def values(self) -> Iterable[Any]:
        yield from self._data.values()

    def get(self, item, default=None):
        if item not in self:
            return default

        return self[item]

    def __str__(self):
        self.load()
        return self._data.__str__()

    def __getattr__(self, item):
        if item != "loaded":
            self.load()
            return self._data.__getattr__(item)
        return self[item]

    def __setattr__(self, key, value):
        if key not in ["_data", "loaded"]:
            self.load()
            self._data.__setattr__(key, value)
            return
        super().__setattr__(key, value)

    def __getitem__(self, item):
        if item != "loaded":
            self.load()
            return self._data.__getitem__(item)
        return getattr(self, item)

    def __setitem__(self, key, value):
        if key != "_data":
            self.load()
            self._data.__setitem__(key, value)
            return
        super().__setitem__(key, value)

    def __iter__(self) -> Iterable[str]:
        self.load()
        yield from self._data.keys()

    def __contains__(self, item):
        self.load()
        return item in self._data


user = ContextVar("Current user", default=None)
