from viur.core.bones import StringBone
from viur.core.tasks import StartupTask
from viur.core import conf, db
from viur.core.skeleton import Skeleton, SkeletonInstance
from viur.core.prototypes import List, BasicApplication


class ModulesConfSkel(Skeleton):
    kindName = "viur-modules-conf"
    name = StringBone()


class ModulesConf(List):
    kindName = "viur-modules-conf"
    accessRights = ["manage"]

    def __init__(self, moduleName, modulePath, *args, **kwargs):
        super(ModulesConf, self).__init__(moduleName, modulePath, *args, **kwargs)

    def canAdd(self):
        return False

    def canDelete(self, skel: SkeletonInstance) -> bool:
        return False

    def canEdit(self, skel: SkeletonInstance) -> bool:
        return False


@StartupTask
def read_all_modules():
    for key in dir(conf["viur.mainApp"].vi):

        app = getattr(conf["viur.mainApp"].vi, key)
        if isinstance(app, BasicApplication):
            dbkey = db.Key("viur-modules-conf", f"{key}")
            if not db.Get(dbkey):
                skel = getattr(conf["viur.mainApp"].vi, "_modulesconf").addSkel()
                skel["key"] = dbkey
                skel["name"] = key
                skel.toDB()


ModulesConf.html = True
ModulesConf.json = True
