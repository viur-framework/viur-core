from .default import DefaultRender as default, serializeXML
from .user import UserRender as user
from viur.core import conf, securitykey, exposed
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
def dumpConfig(adminTree):
    res = {}
    for key in dir(conf["viur.mainApp"].xml):
        app = getattr(adminTree, key)
        if "adminInfo" in dir(app) and app.adminInfo:
            res[key] = app.adminInfo
    return res


def _postProcessAppObj(obj):
    obj["skey"] = genSkey
    obj["timestamp"] = timestamp
    obj["config"] = dumpConfig
    return obj
