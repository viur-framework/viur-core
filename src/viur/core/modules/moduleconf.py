import logging
from viur.core.bones import StringBone, TextBone, SelectBone, TreeLeafBone
from viur.core.bones.text import _defaultTags
from viur.core.tasks import StartupTask
from viur.core import Module, conf, db
from viur.core.i18n import translate
from viur.core.skeleton import Skeleton, SkeletonInstance, RelSkel
from viur.core.prototypes import List


class ScriptRelSkel(RelSkel):

    name = StringBone(
        descr="Label",
        required=True,
        params={
            "tooltip": "Label for the action button displayed."
        },
    )

    icon = StringBone(
        descr="Icon",
        params={
            "tooltip": "Shoelace-conforming icon identifier."
        },
    )

    capable = SelectBone(
        descr="Arguments",
        required=True,
        defaultValue="none",
        values={
            "none": "none: No arguments, always executable",
            "single": "single: Run script with single entry key as argument",
            "multiple": "multiple: Run script with list of entity keys as argument",
        },
        params={
            "tooltip":
                "Describes the behavior in the admin, "
                "if and how selected entries from the module are being processed."
        },
    )

    access = SelectBone(
        descr="Required access rights",
        values=lambda: {
            right: translate(f"server.modules.user.accessright.{right}", defaultText=right)
            for right in sorted(conf["viur.accessRights"])
        },
        multiple=True,
        params={
            "tooltip":
                "To whom the button should be displayed in the admin. "
                "In addition, the admin checks whether all rights of the script are also fulfilled.",
        },
    )


class ModuleConfSkel(Skeleton):
    kindName = "viur-module-conf"

    _valid_tags = ['b', 'a', 'i', 'u', 'span', 'div', 'p', 'ol', 'ul', 'li', 'abbr', 'sub', 'sup', 'h1', 'h2', 'h3',
                   'h4', 'h5', 'h6', 'br', 'hr', 'strong', 'blockquote', 'em']
    _valid_html = _defaultTags.copy()
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

    scripts = TreeLeafBone(
        descr=translate("scriptor scripts"),
        module="script",
        kind="viur-script-leaf",
        using=ScriptRelSkel,
        refKeys=[
            "key",
            "name",
            "access",
        ],
        multiple=True,
    )


class ModuleConf(List):
    """
        This module is for ViUR internal purposes only.
        It lists all other modules to be able to provide them with help texts.
    """
    kindName = "viur-module-conf"
    accessRights = ["edit"]

    def adminInfo(self):
        return conf.moduleconf_admin_info or {}

    def canAdd(self):
        return False

    def canDelete(self, skel: SkeletonInstance) -> bool:
        return False

    @classmethod
    def get_by_module_name(cls, module_name: str) -> None | SkeletonInstance:
        db_key = db.Key("viur-module-conf", module_name)
        skel = conf.main_app._moduleconf.viewSkel()
        if not skel.fromDB(db_key):
            logging.error(f"module({module_name}) not found in viur-module-conf")
            return None

        return skel


@StartupTask
def read_all_modules():
    kind_name = conf.main_app._moduleconf.viewSkel().kindName
    db_module_names = [m["name"] for m in db.Query(kind_name).run(999)]
    visited_modules = set()

    def collect_modules(parent, depth: int = 0, prefix: str = "") -> None:
        """Recursively collects all routable modules for the vi renderer"""
        if depth > 10:
            logging.warning(f"Reached maximum recursion limit of {depth} at {parent=}")
            return

        for module_name in dir(parent):
            module = getattr(parent, module_name, None)
            if not isinstance(module, Module):
                continue
            if module in visited_modules:
                # Some modules reference other modules as parents, this will
                # lead to infinite recursion. We can avoid reaching the
                # maximum recursion limit by remembering already seen modules.
                if conf.debug.trace:
                    logging.debug(f"Already visited and added {module=}")
                continue
            visited_modules.add(module)
            module_path = f"{prefix}{module_name}"
            if module_name not in db_module_names:
                skel = conf.main_app._moduleconf.addSkel()
                skel["key"] = db.Key(kind_name, module_path)
                skel["name"] = module_path
                skel.toDB()

            # Collect children
            collect_modules(module, depth=depth + 1, prefix=f"{module_path}.")

    collect_modules(conf.main_app.vi)


ModuleConf.json = True
