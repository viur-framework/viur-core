from viur.core.bones import StringBone
from viur.core.tasks import StartupTask
from viur.core import conf, db
from viur.core.i18n import translate
from viur.core.skeleton import Skeleton, SkeletonInstance
from viur.core.prototypes import List, BasicApplication


class ModuleConfSkel(Skeleton):
    kindName = "viur-module-conf"
    name = StringBone(descr=translate("modulename"), readOnly=True)
    help_text = StringBone(descr=translate("module helptext"))
    help_text_add = StringBone(descr=translate("add helptext"))
    help_text_edit = StringBone(descr=translate("edit helptext"))
    # seo.....


class ModuleConf(List):
    """
        This module is for ViUR internal purposes only.
        It lists all other modules to be able to provide them with help texts.
    """
    kindName = "viur-module-conf"
    accessRights = ["edit"]

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
                skel = getattr(conf["viur.mainApp"], "_moduleconf").addSkel()
                skel["key"] = db_key
                skel["name"] = module_name
                skel.toDB()


ModuleConf.json = True
