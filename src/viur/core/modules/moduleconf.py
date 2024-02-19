import logging
from viur.core import Module, conf, db, current, i18n, tasks, skeleton
from viur.core.bones import StringBone, TextBone, SelectBone, TreeLeafBone
from viur.core.bones.text import _defaultTags
from viur.core.prototypes import List


MODULECONF_KINDNAME = "viur-module-conf"


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
            right: i18n.translate(f"server.modules.user.accessright.{right}", defaultText=right)
            for right in sorted(conf["viur.accessRights"])
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

    _valid_tags = ['b', 'a', 'i', 'u', 'span', 'div', 'p', 'ol', 'ul', 'li', 'abbr', 'sub', 'sup', 'h1', 'h2', 'h3',
                   'h4', 'h5', 'h6', 'br', 'hr', 'strong', 'blockquote', 'em']
    _valid_html = _defaultTags.copy()
    _valid_html["validTags"] = _valid_tags

    name = StringBone(
        descr=i18n.translate("modulename"),
        readOnly=True,
    )

    help_text = TextBone(
        descr=i18n.translate("module helptext"),
        validHtml=_valid_html,
    )

    help_text_add = TextBone(
        descr=i18n.translate("add helptext"),
        validHtml=_valid_html,
    )

    help_text_edit = TextBone(
        descr=i18n.translate("edit helptext"),
        validHtml=_valid_html,
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

    def adminInfo(self):
        return conf.get("viur.moduleconf.admin_info") or {}

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
        skel = conf["viur.mainApp"]._moduleconf.viewSkel()
        if not skel.fromDB(db_key):
            logging.error(f"module({module_name}) not found")
            return None

        return skel

    @tasks.StartupTask
    @staticmethod
    def read_all_modules():
        db_module_names = (m["name"] for m in db.Query(MODULECONF_KINDNAME).run(999))
        module_names = dir(conf["viur.mainApp"].vi)

        for module_name in module_names:
            module = getattr(conf["viur.mainApp"].vi, module_name)
            if isinstance(module, Module):
                ModuleConf.MODULES.add(module_name)

                if module_name not in db_module_names:
                    skel = conf["viur.mainApp"]._moduleconf.addSkel()
                    skel["key"] = db.Key(MODULECONF_KINDNAME, module_name)
                    skel["name"] = module_name
                    skel.toDB()

        # TODO: Remove entries from MODULECONF_KINDNAME which are in db_module_names but not in ModuleConf.MODULES


ModuleConf.json = True
