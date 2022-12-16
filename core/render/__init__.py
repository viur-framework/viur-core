from . import html
from . import admin
from . import xml
from . import json
from . import vi
from viur.core import conf


def isViAvailable():
    return conf["viur.instance.project_base_path"].joinpath("vi", "main.html").exists()


def isAdminAvailable():
    return conf["viur.instance.project_base_path"].joinpath("admin", "admin.html").exists()


__all__ = ["html", "admin", "xml", "json", "vi", "isViAvailable", "isAdminAvailable"]
