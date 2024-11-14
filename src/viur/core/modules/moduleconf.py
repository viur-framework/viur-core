import logging
import typing as t
from viur.core import Module, conf, db, current, i18n, tasks, skeleton
from viur.core.bones import StringBone, TextBone, SelectBone, TreeLeafBone
from viur.core.bones.text import HtmlBoneConfiguration
from viur.core.prototypes import List


MODULECONF_KINDNAME = "viur-module-conf"

_LIMITED_HTML: t.Final[HtmlBoneConfiguration] = conf.bone_html_default_allow | {
    "validTags": "a abbr b blockquote br div em h1 h2 h3 h4 h5 h6 hr i li ol p span strong sub sup u ul".split(),
}


class ModuleConfScriptSkel(skeleton.RelSkel):

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
            right: i18n.translate(f"viur.modules.user.accessright.{right}", defaultText=right)
            for right in sorted(conf.user.access_rights)
        },
        multiple=True,
        params={
            "tooltip":
                "To whom the button should be displayed in the admin. "
                "In addition, the admin checks whether all rights of the script are also fulfilled.",
        },
    )


class ModuleConfSkel(skeleton.Skeleton):
    kindName = MODULECONF_KINDNAME

    name = StringBone(
        descr=i18n.translate("modulename"),
        readOnly=True,
    )

    help_text = TextBone(
        descr=i18n.translate("module helptext"),
        validHtml=_LIMITED_HTML,
    )

    help_text_add = TextBone(
        descr=i18n.translate("add helptext"),
        validHtml=_LIMITED_HTML,
    )

    help_text_edit = TextBone(
        descr=i18n.translate("edit helptext"),
        validHtml=_LIMITED_HTML,
    )

    scripts = TreeLeafBone(
        descr=i18n.translate("scriptor scripts"),
        module="script",
        kind="viur-script-leaf",
        using=ModuleConfScriptSkel,
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
    MODULES = set()  # will be filled by read_all_modules
    kindName = MODULECONF_KINDNAME
    accessRights = ["edit"]
    default_order = None  # disable default ordering for ModuleConf

    def adminInfo(self):
        return conf.moduleconf_admin_info or {}

    def canAdd(self):
        return False

    def canDelete(self, skel):
        return False

    def canEdit(self, skel):
        if super().canEdit(skel):
            return True

        # Check for "manage"-flag on current user
        return (cuser := current.user.get()) and f"""{skel["name"]}-manage""" in cuser["access"]

    def listFilter(self, query):
        original_query = query

        # when super-call does not satisfy...
        if not (query := super().listFilter(query)):
            if cuser := current.user.get():
                # ... then, list modules the user is allowed to use!
                user_modules = set(right.split("-", 1)[0] for right in cuser["access"] if "-" in right)

                query = original_query
                query.filter("name IN", tuple(user_modules))

        return query

    @classmethod
    def get_by_module_name(cls, module_name: str) -> None | skeleton.SkeletonInstance:
        db_key = db.Key(MODULECONF_KINDNAME, module_name)
        skel = conf.main_app.vi._moduleconf.viewSkel()
        if not skel.read(db_key):
            logging.error(f"module({module_name}) not found")
            return None

        return skel

    @tasks.StartupTask
    @staticmethod
    def read_all_modules():
        db_module_names = (m["name"] for m in db.Query(MODULECONF_KINDNAME).run(999))
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
                module_name = f"{prefix}{module_name}"
                visited_modules.add(module)
                ModuleConf.MODULES.add(module_name)
                if module_name not in db_module_names:
                    skel = conf.main_app.vi._moduleconf.addSkel()
                    skel["key"] = db.Key(MODULECONF_KINDNAME, module_name)
                    skel["name"] = module_name
                    skel.write()

                # Collect children
                collect_modules(module, depth=depth + 1, prefix=f"{module_name}.")

        collect_modules(conf.main_app.vi)
        # TODO: Remove entries from MODULECONF_KINDNAME which are in db_module_names but not in ModuleConf.MODULES
