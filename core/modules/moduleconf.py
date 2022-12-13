import logging

from viur.core.bones import StringBone, TextBone
from viur.core.bones.text import _defaultTags
from viur.core.tasks import StartupTask
from viur.core import conf, db
from viur.core.i18n import translate
from viur.core.skeleton import Skeleton, SkeletonInstance
from viur.core.prototypes import List, BasicApplication


class ModuleConfSkel(Skeleton):
    kindName = "viur-module-conf"

    _valid_tags = ['b', 'a', 'i', 'u', 'span', 'div', 'p', 'ol', 'ul', 'li', 'abbr', 'sub', 'sup', 'h1', 'h2', 'h3',
                   'h4', 'h5', 'h6', 'br', 'hr', 'strong', 'blockquote', 'em']
    _valid_html = _defaultTags
    _valid_html["validTags"] = _valid_tags

    name = StringBone(
        descr=translate("modulename"),
        readOnly=True,
    )

    help_text = TextBone(
        descr=translate("module helptext"),
        validHtml=_valid_html,
    )

    help_text_add = TextBone(
        descr=translate("add helptext"),
        validHtml=_valid_html,
    )

    help_text_edit = TextBone(
        descr=translate("edit helptext"),
        validHtml=_valid_html,
    )


class ModuleConf(List):
    """
        This module is for ViUR internal purposes only.
        It lists all other modules to be able to provide them with help texts.
    """
    kindName = "viur-module-conf"
    accessRights = ["edit"]

    def adminInfo(self):
        return super().adminInfo() | conf.get("viur.moduleconf.admin_info") or {}

    def canAdd(self):
        return False

    def canDelete(self, skel: SkeletonInstance) -> bool:
        return False

    @classmethod
    def get_by_module_name(cls, module_name: str) -> None | SkeletonInstance:
        db_key = db.Key("viur-module-conf", module_name)
        skel = conf["viur.mainApp"]._moduleconf.viewSkel()
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
                skel = conf["viur.mainApp"]._moduleconf.addSkel()
                skel["key"] = db.Key("viur-module-conf", app_module_name)
                skel["name"] = app_module_name
                skel.toDB()


ModuleConf.json = True
