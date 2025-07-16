import io
import typing as t
from viur.core.bones import *
from viur.core.prototypes.tree import Tree, TreeSkel, SkelType
from viur.core.modules.file import File
from viur.core import db, conf, current, skeleton, tasks, errors
from viur.core.decorators import exposed
from viur.core.i18n import translate
import zipfile


class BaseScriptAbstractSkel(TreeSkel):
    path = StringBone(
        descr="Path",
        readOnly=True,
        unique=UniqueValue(UniqueLockMethod.SameValue, True, "This path is already taken!")
    )

    @classmethod
    def fromClient(cls, skel, data, *args, **kwargs):
        # Set script name when provided, so that the path can be regenerated
        if name := data.get("name"):
            skel["name"] = name
            conf.main_app.script.update_path(skel)

        ret = super().fromClient(skel, data, *args, **kwargs)

        if not ret:
            # in case the path failed because the unique value is already taken, rewrite the error for name field
            for error in skel.errors:
                if error.severity == ReadFromClientErrorSeverity.Invalid and error.fieldPath == ["path"]:
                    error.fieldPath = ["name"]
                    break

        return ret


class ScriptNodeSkel(BaseScriptAbstractSkel):
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
        vfunc=lambda value: None if File.is_valid_filename(value) else "Foldername is invalid"
    )


class ScriptLeafSkel(BaseScriptAbstractSkel):
    kindName = "viur-script-leaf"

    name = StringBone(
        descr="Filename",
        required=True,
        vfunc=lambda value:
            None if File.is_valid_filename(value) and value.endswith(".py") and value.removesuffix(".py")
            else "Filename is invalid or doesn't have a '.py'-suffix",
    )

    script = RawBone(
        descr="Code",
        indexed=False,
    )

    access = SelectBone(
        descr="Required access rights to run this Script",
        values=lambda: {
            right: translate(f"viur.core.modules.user.accessright.{right}", defaultText=right)
            for right in sorted(conf.user.access_rights)
        },
        multiple=True,
    )


class Script(Tree):
    """
    Script is a system module used to serve a filesystem for scripts used by ViUR Scriptor and ViUR CLI.
    """

    leafSkelCls = ScriptLeafSkel
    nodeSkelCls = ScriptNodeSkel

    roles = {
        "admin": "*",
    }

    def adminInfo(self):
        return conf.script_admin_info or {}

    def getAvailableRootNodes(self):
        if not current.user.get():
            return []

        return [{
            "name": "Scripts",
            "key": self.rootnodeSkel(ensure=True)["key"],
        }]

    @exposed
    def view(self, skelType: SkelType, key: db.Key | int | str, *args, **kwargs) -> t.Any:
        try:
            return super().view(skelType, key, *args, **kwargs)
        except errors.NotFound:
            # When key is not found, try to interpret key as path
            if skel := self.viewSkel(skelType).all().mergeExternalFilter({"path": key}).getSkel():
                return super().view(skelType, skel["key"], *args, **kwargs)

            raise

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
                skel.write()
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
            if not parent_skel.read(key) or parent_skel["key"] == skel["parentrepo"]:
                break

            path.insert(0, parent_skel["name"])
            key = parent_skel["parententry"]

        skel["path"] = "/".join(path)

    @exposed
    def get_importable(self):

        # get importable key
        qry_importable = (self.viewSkel("node").all()
                          .filter("parententry", self.rootnodeSkel(ensure=True)["key"])
                          .filter("name =", "importable"))
        if not (qry_importable := self.listFilter(qry_importable)):
            raise errors.Unauthorized()

        importable_key = (entity := qry_importable.getEntry()) and entity.key

        def get_files_recursively(_importable_key):
            res = []
            importable_files_query = self.viewSkel("leaf").all().filter("parententry", _importable_key)
            if not (importable_files_query := self.listFilter(importable_files_query)):
                raise errors.Unauthorized()
            for script_entry in importable_files_query.iter():
                if script_entry["script"]:
                    res.append(script_entry)
            importable_files_query = self.viewSkel("node").all().filter("parententry", _importable_key)
            for folder_entry in importable_files_query.iter():
                res.extend(get_files_recursively(folder_entry.key))
            return res

        importable_files = get_files_recursively(importable_key)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for file in importable_files:
                zip_file.writestr(file["path"], file["script"])

        current.request.get().response.headers["Content-Disposition"] = "attachment; filename=importable.zip"
        current.request.get().response.headers["Content-Type"] = "application/zip"
        return zip_buffer.getvalue()
