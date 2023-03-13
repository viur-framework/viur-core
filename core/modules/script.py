from viur.core import Module, skeleton
from viur.core.bones import *
from viur.core.prototypes.tree import Tree, TreeSkel
from viur.core import db, utils, conf, skeleton, tasks, i18n
from viur.core.prototypes.tree import Tree
import re
import os


# pre-compile patterns for vfuncs
DIRECTORY_PATTERN = re.compile(r'^[a-zA-Z0-9äöüÄÖÜ_-]*$')
FILE_PATTERN = re.compile(r'^[a-zA-Z0-9äöüÄÖÜ_-]+?.py$')


def _get_modules():
    res = {}

    for key in dir(conf["viur.mainApp"].vi):
        module = getattr(conf["viur.mainApp"].vi, key, None)
        if not isinstance(module, Module):
            continue

        if admin_info := module.describe():
            res[key] = admin_info

    return res


def _get_modules_or_handlers():
    modules = _get_modules()

    ret = {}
    for name, mod in modules.items():
        handler = mod["handler"].split(".", 1)[0]
        if f"@{handler}" not in ret:
            ret[f"@{handler}"] = f"All {handler} modules"

            if handler == "tree":
                for t in ("node", "leaf"):
                    ret[f"@{handler}.{t}"] = f"""All {handler} modules - {t} only"""

        ret[name] = mod["name"]
        if handler == "tree":
            for t in ("node", "leaf"):
                ret[f"{name}.{t}"] = f"""{mod["name"]} - {t}"""

    return {k: v for k, v in sorted(ret.items(), key=lambda item: item[0])}


class BaseScriptAbstractSkel(TreeSkel):

    path = StringBone(
        descr="Path",
        readOnly=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, True, "This path name is already taken!")
    )

    @classmethod
    def fromClient(cls, skel, data, *args, **kwargs):
        # Set script name when provided, so that the path can be regenerated
        if name := data.get("name"):
            skel["name"] = name
            conf["viur.mainApp"].vi.script.update_path(skel)

        ret = super().fromClient(skel, data, *args, **kwargs)

        if not ret:
            # in case the path failed because the unique value is already taken, rewrite the error for name field
            for error in skel.errors:
                if error.severity == skeleton.ReadFromClientErrorSeverity.Invalid and error.fieldPath == ["path"]:
                    error.fieldPath = ["name"]
                    break

        return ret


class ScriptNodeSkel(BaseScriptAbstractSkel):
    kindName = "viur-script-node"

    rootNode = BooleanBone(
        descr="Is root node?",
        defaultValue=False,
    )

    name = StringBone(
        descr="Folder",
        required=True,
        vfunc=lambda value: not DIRECTORY_PATTERN.match(value)
    )


class ScriptLeafActionSkel(skeleton.RelSkel):
    module = SelectBone(
        descr="Modul",
        values=_get_modules_or_handlers
    )
    capable = SelectBone(
        descr="Capable to handle",
        values={
            "none": "Run action without further parameters.",
            "single": "Script may use one entity key in parameters",
            "multiple": "Script may use several entity keys in parameters"
        }
    )
    thismoduleaccess = SelectBone(
        descr="Required access rights of specific modules",
        values=["view", "add", "edit", "delete"],
        multiple=True,
    )


class ScriptLeafSkel(BaseScriptAbstractSkel):
    kindName = "viur-script-leaf"

    name = StringBone(
        descr="Filename",
        vfunc=lambda value: not FILE_PATTERN.match(value),
    )

    globalid = StringBone(
        descr="Global identifyer",
        vfunc=lambda value: not FILE_PATTERN.match(value),
        # unique=True,
        params={
            "tooltip": "If the script got copied from an other scriptreository, you may want to set an "
            "unique identifyer so you may match it for updates."
                }
    )

    label = StringBone(
        descr="Button label",
        defaultValue="Run script",
        )

    tooltip = TextBone(
        descr="Tooltip for button",
        validHtml=None,
        )

    icon = SelectBone(
        descr="Icon",
        values=[icon.removesuffix(".svg") for icon in sorted(os.listdir("static/svg"))],
        params={
                "tooltip": "Icon which is used by /vi to display in the Buttonbar."
            }
        )

    buttonbar = RecordBone(
        descr="Visible in Buttonbar",
        multiple=True,
        using=ButtonbarSkel,
        required=False,
        format="$(module)",
        )

    userdescr = TextBone(descr="Description for user")
    devdescr = TextBone(descr="Description for developers ")

    globalaccess = SelectBone(
        descr="Required access rights of specific modules",
        values=lambda: {

            right: i18n.translate("server.modules.user.accessright.%s" % right, defaultText=right)
            for right in sorted(conf["viur.accessRights"])
        },
        multiple=True,
    )

    script = RawBone(
        descr="Code",
        indexed=False
    )


class Script(Tree):
    leafSkelCls = ScriptLeafSkel
    nodeSkelCls = ScriptNodeSkel

    accessRights = ("add", "edit", "view", "delete", "run")

    def adminInfo(self):
        return conf.get("viur.script.admin_info") or {}

    def getAvailableRootNodes(self):
        if not utils.getCurrentUser():
            return []

        return [{"name": "Scripts", "key": self.ensureOwnModuleRootNode().key}]

    def onEdit(self, skelType, skel):
        self.update_path(skel)
        super().onEdit(skelType, skel)

    def onEdited(self, skelType, skel):
        if skelType == "node":
            self.update_path_recursive("node", skel["path"], skel["key"])
            self.update_path_recursive("leaf", skel["path"], skel["key"])

        super().onEdited(skelType, skel)

    @tasks.CallDeferred
    def update_path_recursive(self, skel_type, path, parent_key, cursor=None):
        """
        Recursively updates all items under a given parent key.
        """
        query = self.editSkel(skel_type).all().filter("parententry", parent_key)
        query.setCursor(cursor)

        for skel in query.fetch(99):
            new_path = path + "/" + skel["name"]

            # only update when path changed
            if new_path != skel["path"]:
                skel["path"] = new_path  # self.onEdit() is NOT required, as it resolves the path again.
                skel.toDB()
                self.onEdited(skel_type, skel)  # triggers this recursion for nodes, again.

        if cursor := query.getCursor():
            self.update_path_recursive(skel_type, path, parent_key, cursor)

    def update_path(self, skel):
        """
        Updates the path-value of a either a folder or a script file, by resolving the repository's root node.
        """
        path = [skel["name"]]

        key = skel["parententry"]
        while key:
            parent_skel = self.viewSkel("node")
            if not parent_skel.fromDB(key) or parent_skel["key"] == skel["parentrepo"]:
                break

            path.insert(0, parent_skel["name"])
            key = parent_skel["parententry"]

        skel["path"] = "/".join(path)


Script.json = True
