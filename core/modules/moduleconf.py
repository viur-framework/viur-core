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

    for db_module_name in db_module_names:
        if db_module_name not in app_module_names:
            skel = getattr(conf["viur.mainApp"], "_moduleconf").editSkel()
            if skel.fromDB(db.Key("viur-module-conf", f"{db_module_name}")):
                skel.delete()


ModuleConf.json = True
