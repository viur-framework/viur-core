from viur.core.bones import *
from viur.core.prototypes.tree import Tree, TreeSkel
from viur.core import db, utils, conf, skeleton
from viur.core.prototypes.tree import Tree
import re


# pre-compile patterns for vfuncs
DIRECTORY_PATTERN = re.compile(r'^[a-zA-Z0-9äöüÄÖÜ_-]*$')
FILE_PATTERN = re.compile(r'^[a-zA-Z0-9äöüÄÖÜ_-]+?.py$')


def utils_get_path(skel, data = None):
    script: Tree = conf["viur.mainApp"].vi.script

    path = ""
    if skel["parententry"] != skel["parentrepo"]:
        _parents = script.path_to_key(skel["parententry"])

        for parent in _parents:
            if not parent["rootNode"]:
                path += parent["name"] + "/"

    if data:
        if "name" in data:
            path += data["name"]
        else:
            if skel and "name" in skel:
                path += skel["name"]
    elif skel:
        if skel["name"]:
            path += skel["name"]

    return path


class BaseScriptAbstractSkel(TreeSkel):
    PATH_SUFFIX = ""

    path = StringBone(
        descr="Path",
        required=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, True, "The entered file name already exists.")
    )

    @classmethod
    def set_path(cls, skel, data):
        skel["path"] = utils_get_path(skel, data) + cls.PATH_SUFFIX

        if data:
            data["path"] = skel["path"]

    @classmethod
    def fromClient(cls, skel, data, *args, **kwargs):
        cls.set_path(skel, data)

        ret = super().fromClient(skel, data, *args, **kwargs)

        if not ret:
            # in case the identifier failed because the unique value is already provided, rewrite the error for variable
            for error in skel.errors:
                if error.severity == skeleton.ReadFromClientErrorSeverity.Invalid and error.fieldPath == ["path"]:
                    error.fieldPath = ["path"]
                    break

        return ret


class ScriptNodeSkel(BaseScriptAbstractSkel):
    PATH_SUFFIX = "/"
    kindName = "viur-script-node"

    rootNode = BooleanBone(
        descr="Is root node?",
        defaultValue=False,
    )

    plugin = BooleanBone(
        descr="Is plugin?",
        defaultValue=False
    )

    name = StringBone(
        descr="Folder",
        required=True,
        vfunc=lambda value: not DIRECTORY_PATTERN.match(value)
    )


class ScriptLeafSkel(BaseScriptAbstractSkel):
    kindName = "viur-script-leaf"

    name = StringBone(
        descr="Filename",
        vfunc=lambda value: not FILE_PATTERN.match(value),
    )

    script = RawBone(
        descr="Code",
        indexed=False
    )


class Script(Tree):
    leafSkelCls = ScriptLeafSkel
    nodeSkelCls = ScriptNodeSkel

    def adminInfo(self):
        return conf.get("viur.script.admin_info") or {}

    def getAvailableRootNodes(self):
        if not utils.getCurrentUser():
            return []

        return [{"name": "Scripts", "key": self.ensureOwnModuleRootNode().key}]

    def onEdit(self, skelType, skel):
        path = utils_get_path(skel)
        if skelType == "node":
            path += ScriptNodeSkel.PATH_SUFFIX

        skel["path"] = path

    def onEdited(self, skelType, skel):
        if skelType == "node":
            query = self.editSkel("node").all().filter("parententry =", skel["key"])

            for entry in query.fetch(99):
                self.onEdit("node", entry)
                entry.toDB()

            query = self.editSkel("leaf").all().filter("parententry =", skel["key"])
            for entry in query.fetch(99):
                self.onEdit("leaf", entry)
                entry.toDB()

    def path_to_key(self, key: db.Key):
        """
        Retrieve the path from a node to the root.
        """
        parents = []

        while key:
            skel = self.viewSkel("node")
            if not skel.fromDB(key) or skel["key"] == skel["parentrepo"]:  # We reached the top level
                break

            parents.append(skel)
            key = skel["parententry"]

        return parents.reverse()


Script.json = True
