from viur.core.bones import StringBone
from viur.core.tasks import StartupTask
from viur.core import conf, db
from viur.core.i18n import translate
from viur.core.skeleton import Skeleton, SkeletonInstance
from viur.core.prototypes import List, BasicApplication


class ModulesConfSkel(Skeleton):
    kindName = "viur-modules-conf"
    name = StringBone(descr=translate("modulename"), readOnly=True)
    help_text = StringBone(descr=translate("module helptext"))
    help_text_add = StringBone(descr=translate("add helptext"))
    help_text_edit = StringBone(descr=translate("edit helptext"))
    # seo.....


class ModulesConf(List):
    kindName = "viur-modules-conf"
    accessRights = ["manage"]

    def canAdd(self):
        return False

    def canDelete(self, skel: SkeletonInstance) -> bool:
        return False


@StartupTask
def read_all_modules():
    for module_name in dir(conf["viur.mainApp"].vi):
        app = getattr(conf["viur.mainApp"].vi, module_name)
        if isinstance(app, BasicApplication):
            db_key = db.Key("viur-modules-conf", f"{module_name}")
            if not db.Get(db_key):
                skel = getattr(conf["viur.mainApp"], "_modulesconf").addSkel()
                skel["key"] = db_key
                skel["name"] = module_name
                skel.toDB()


ModulesConf.json = True
