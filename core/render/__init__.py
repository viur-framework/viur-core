from . import html
from . import admin
from . import xml
from . import json
from . import vi
from os import path
from viur.core import conf

def isViAvailable():
    return path.exists(path.join(conf["viur.instance.core_base_path"], "vi", "main.html"))


def isAdminAvailable():
    return path.exists(path.join(conf["viur.instance.core_base_path"], "admin", "admin.html"))


__all__ = ["html", "admin", "xml", "json", "vi", "isViAvailable", "isAdminAvailable"]
