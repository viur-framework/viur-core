from . import html
from . import admin
from . import xml
from . import json
from . import vi
from os import path


def isViAvailable():
    from viur.core.utils import projectBasePath
    return path.exists(path.join(projectBasePath, "vi", "main.html"))


def isAdminAvailable():
    from viur.core.utils import projectBasePath
    return path.exists(path.join(projectBasePath, "admin", "admin.html"))


__all__ = ["html", "admin", "xml", "json", "vi", "isViAvailable", "isAdminAvailable"]
