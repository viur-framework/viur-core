from .default import DefaultRender as default, serializeXML
from .user import UserRender as user
from viur.core import Module, conf, securitykey
from viur.core.decorators import *
import datetime

__all__ = [default]


@exposed
def genSkey(*args, **kwargs):
    return f"<securityKey>{securitykey.create()}</securityKey>"


@exposed
def timestamp(*args, **kwargs):
    d = datetime.datetime.now()
    return serializeXML(d.strftime("%Y-%m-%dT%H-%M-%S"))


@exposed
def dumpConfig():
    res = {}
    for key in dir(conf.main_app.xml):
        module = getattr(conf.main_app.xml, key)
        if not isinstance(module, Module):
            continue
        if admin_info := module.describe():
            res[key] = admin_info

    res = {
        "modules": res,
        "configuration": {
            k.removeprefix("admin."): v for k, v in conf.items() if k.lower().startswith("admin.")
        }
    }
    return res


def _postProcessAppObj(obj):
    obj["skey"] = genSkey
    obj["timestamp"] = timestamp
    obj["config"] = dumpConfig
    return obj
