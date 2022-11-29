from .default import DefaultRender as default, serializeXML
from .user import UserRender as user
from viur.core import conf
from viur.core import securitykey
import datetime

__all__ = [default]


def genSkey(*args, **kwargs):
    return "<securityKey>%s</securityKey>" % securitykey.create()


genSkey.exposed = True


def timestamp(*args, **kwargs):
    d = datetime.datetime.now()
    return serializeXML(d.strftime("%Y-%m-%dT%H-%M-%S"))


timestamp.exposed = True


def generateAdminConfig(adminTree):
    res = {}
    for key in dir(adminTree):
        app = getattr(adminTree, key)
        if "adminInfo" in dir(app) and app.adminInfo:
            res[key] = app.adminInfo
    return res


def dumpConfig(adminConfig):
    return serializeXML({
        "modules": adminConfig
    })


def _postProcessAppObj(obj):
    obj["skey"] = genSkey
    obj["timestamp"] = timestamp
    adminConfig = generateAdminConfig(obj)
    tmp = lambda *args, **kwargs: dumpConfig(adminConfig)
    tmp.exposed = True
    obj["config"] = tmp
    return obj
