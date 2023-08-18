from .default import DefaultRender as default, serializeXML
from .user import UserRender as user
from viur.core import Module, conf, securitykey, exposed
import datetime

__all__ = [default]


@exposed
def genSkey(*args, **kwargs):
    return "<securityKey>%s</securityKey>" % securitykey.create()


@exposed
def timestamp(*args, **kwargs):
    d = datetime.datetime.now()
    return serializeXML(d.strftime("%Y-%m-%dT%H-%M-%S"))


@exposed
def dumpConfig():
    res = {}
    for key in dir(conf["viur.mainApp"].xml):
        module = getattr(conf["viur.mainApp"].xml, key)
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
