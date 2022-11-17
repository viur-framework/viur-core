import logging

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

    @classmethod
    def get_by_module_name(cls, module_name: str):
        db_key = db.Key("viur-module-conf", f"{module_name}")
        skel = getattr(conf["viur.mainApp"], "_moduleconf").viewSkel()
        if not skel.fromDB(db_key):
            logging.error(f"module({module_name}) not found in viur-module-conf")
            return None
        return skel

@StartupTask
def read_all_modules():
    db_module_names = [m["name"] for m in db.Query("viur-module-conf").run(999)]
    app_module_names = dir(conf["viur.mainApp"].vi)

    for app_module_name in app_module_names:
        app = getattr(conf["viur.mainApp"].vi, app_module_name)
        if isinstance(app, BasicApplication):
            if app_module_name not in db_module_names:
                skel = getattr(conf["viur.mainApp"], "_moduleconf").addSkel()
                skel["key"] = db.Key("viur-module-conf", f"{app_module_name}")
                skel["name"] = app_module_name
                skel.toDB()


ModuleConf.json = True
