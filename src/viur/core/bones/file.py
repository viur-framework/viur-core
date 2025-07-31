"""
The FileBone is a subclass of the TreeLeafBone class, which is a relational bone that can reference
another entity's fields. FileBone provides additional file-specific properties and methods, such as
managing file derivatives, handling file size and mime type restrictions, and refreshing file
metadata.
"""
import hashlib
import warnings
import time
import typing as t
from viur.core import conf, db, current, utils
from viur.core.bones.treeleaf import TreeLeafBone
from viur.core.tasks import CallDeferred
import logging


@CallDeferred
def ensureDerived(key: db.Key, src_key, derive_map: dict[str, t.Any], refresh_key: db.Key = None, **kwargs):
    r"""
    The function is a deferred function that ensures all pending thumbnails or other derived files
    are built. It takes the following parameters:

    :param db.key key: The database key of the file-object that needs to have its derivation map
        updated.
    :param str src_key: A prefix for a stable key to prevent rebuilding derived files repeatedly.
    :param dict[str,Any] derive_map: A list of DeriveDicts that need to be built or updated.
    :param db.Key refresh_key: If set, the function fetches and refreshes the skeleton after
        building new derived files.

    The function works by fetching the skeleton of the file-object, checking if it has any derived
    files, and updating the derivation map accordingly. It iterates through the derive_map items and
    calls the appropriate deriver function. If the deriver function returns a result, the function
    creates a new or updated resultDict and merges it into the file-object's metadata. Finally,
    the updated results are written back to the database and the update_relations function is called
    to ensure proper relations are maintained.
    """
    # TODO: Remove in VIUR4
    for _dep, _new in {
        "srcKey": "src_key",
        "deriveMap": "derive_map",
        "refreshKey": "refresh_key",
    }.items():
        if _dep in kwargs:
            warnings.warn(
                f"{_dep!r} parameter is deprecated, please use {_new!r} instead",
                DeprecationWarning, stacklevel=2
            )

            locals()[_new] = kwargs.pop(_dep)
    from viur.core.skeleton.utils import skeletonByKind
    from viur.core.skeleton.tasks import update_relations

    skel = skeletonByKind(key.kind)()
    if not skel.read(key):
        logging.info("File-Entry went missing in ensureDerived")
        return
    if not skel["derived"]:
        logging.info("No Derives for this file")
        skel["derived"] = {}
    skel["derived"] = {"deriveStatus": {}, "files": {}} | skel["derived"]
    res_status, res_files = {}, {}
    for call_key, params in derive_map.items():
        full_src_key = f"{src_key}_{call_key}"
        params_hash = hashlib.sha256(str(params).encode("UTF-8")).hexdigest()  # Hash over given params (dict?)
        if skel["derived"]["deriveStatus"].get(full_src_key) != params_hash:
            if not (caller := conf.file_derivations.get(call_key)):
                logging.warning(f"File-Deriver {call_key} not found - skipping!")
                continue

            if call_res := caller(skel, skel["derived"]["files"], params):
                assert isinstance(call_res, list), "Old (non-list) return value from deriveFunc"
                res_status[full_src_key] = params_hash
                for file_name, size, mimetype, custom_data in call_res:
                    res_files[file_name] = {
                        "size": size,
                        "mimetype": mimetype,
                        "customData": custom_data  # TODO: Rename in VIUR4
                    }

    if res_status:  # Write updated results back and queue updateRelationsTask
        def _merge_derives(patch_skel):
            patch_skel["derived"] = {"deriveStatus": {}, "files": {}} | (patch_skel["derived"] or {})
            patch_skel["derived"]["deriveStatus"] = patch_skel["derived"]["deriveStatus"] | res_status
            patch_skel["derived"]["files"] = patch_skel["derived"]["files"] | res_files

        skel.patch(values=_merge_derives, update_relations=False)

        # Queue that update_relations call at least 30 seconds into the future, so that other ensureDerived calls from
        # the same FileBone have the chance to finish, otherwise that update_relations Task will call postSavedHandler
        # on that FileBone again - re-queueing any ensureDerivedCalls that have not finished yet.

        if refresh_key:
            skel = skeletonByKind(refresh_key.kind)()
            skel.patch(lambda _skel: _skel.refresh(), key=refresh_key, update_relations=False)

        update_relations(key, min_change_time=int(time.time() + 1), changed_bones=["derived"], _countdown=30)


class FileBone(TreeLeafBone):
    r"""
    A FileBone is a custom bone class that inherits from the TreeLeafBone class, and is used to store and manage
    file references in a ViUR application.

    :param format: Hint for the UI how to display a file entry (defaults to it's filename)
    :param maxFileSize:
        The maximum filesize accepted by this bone in bytes. None means no limit.
        This will always be checked against the original file uploaded - not any of it's derivatives.

    :param derive: A set of functions used to derive other files from the referenced ones. Used fe.
        to create thumbnails / images for srcmaps from hires uploads. If set, must be a dictionary from string
        (a key from conf.file_derivations) to the parameters passed to that function. The parameters can be
        any type (including None) that can be json-serialized.

        ..  code-block:: python

            # Example
            derive = { "thumbnail": [{"width": 111}, {"width": 555, "height": 666}]}

    :param validMimeTypes:
        A list of Mimetypes that can be selected in this bone (or None for any) Wildcards ("image\/*") are supported.

        ..  code-block:: python

            # Example
            validMimeTypes=["application/pdf", "image/*"]

    """

    kind = "file"
    """The kind of this bone is 'file'"""

    type = "relational.tree.leaf.file"
    """The type of this bone is 'relational.tree.leaf.file'."""

    def __init__(
        self,
        *,
        derive: None | dict[str, t.Any] = None,
        maxFileSize: None | int = None,
        validMimeTypes: None | list[str] = None,
        refKeys: t.Optional[t.Iterable[str]] = (
            "name",
            "mimetype",
            "size",
            "width",
            "height",
            "derived",
            "public",
            "serving_url",
        ),
        public: bool = False,
        **kwargs
    ):
        r"""
        Initializes a new Filebone. All properties inherited by RelationalBone are supported.

        :param format: Hint for the UI how to display a file entry (defaults to it's filename)
        :param maxFileSize: The maximum filesize accepted by this bone in bytes. None means no limit.
        This will always be checked against the original file uploaded - not any of it's derivatives.
        :param derive: A set of functions used to derive other files from the referenced ones.
        Used to create thumbnails and images for srcmaps from hires uploads.
        If set, must be a dictionary from string (a key from) conf.file_derivations) to the parameters passed to
        that function. The parameters can be any type (including None) that can be json-serialized.

        ..  code-block:: python

            # Example
            derive = {"thumbnail": [{"width": 111}, {"width": 555, "height": 666}]}

        :param validMimeTypes:
            A list of Mimetypes that can be selected in this bone (or None for any).
            Wildcards `('image\*')` are supported.

            ..  code-block:: python

                #Example
                validMimeTypes=["application/pdf", "image/*"]

        """
        super().__init__(refKeys=refKeys, **kwargs)

        self.refKeys.add("dlkey")
        self.derive = derive
        self.public = public
        self.validMimeTypes = validMimeTypes
        self.maxFileSize = maxFileSize

    def isInvalid(self, value):
        """
        Checks if the provided value is invalid for this bone based on its MIME type and file size.

        :param dict value: The value to check for validity.
        :returns: None if the value is valid, or an error message if it is invalid.
        """
        if self.validMimeTypes:
            mimeType = value["dest"]["mimetype"]
            for checkMT in self.validMimeTypes:
                checkMT = checkMT.lower()
                if checkMT == mimeType or checkMT.endswith("*") and mimeType.startswith(checkMT[:-1]):
                    break
            else:
                return "Invalid filetype selected"
        if self.maxFileSize:
            if value["dest"]["size"] > self.maxFileSize:
                return "File too large."

        if value["dest"]["public"] != self.public:
            return f"Only files marked public={self.public!r} are allowed."

        return None

    def postSavedHandler(self, skel, boneName, key):
        """
        Handles post-save processing for the FileBone, including ensuring derived files are built.

        :param SkeletonInstance skel: The skeleton instance this bone belongs to.
        :param str boneName: The name of the bone.
        :param db.Key key: The datastore key of the skeleton.

        This method first calls the postSavedHandler of its superclass. Then, it checks if the
        derive attribute is set and if there are any values in the skeleton for the given bone. If
        so, it handles the creation of derived files based on the provided configuration.

        If the values are stored as a dictionary without a "dest" key, it assumes a multi-language
        setup and iterates over each language to handle the derived files. Otherwise, it handles
        the derived files directly.
        """
        super().postSavedHandler(skel, boneName, key)
        if (
            current.request.get().is_deferred
            and "derived" in (current.request_data.get().get("__update_relations_bones") or ())
        ):
            return

        from viur.core.skeleton import RelSkel, Skeleton

        if issubclass(skel.skeletonCls, Skeleton):
            prefix = f"{skel.kindName}_{boneName}"
        elif issubclass(skel.skeletonCls, RelSkel):  # RelSkel is just a container and has no kindname
            prefix = f"{skel.skeletonCls.__name__}_{boneName}"
        else:
            raise NotImplementedError(f"Cannot handle {skel.skeletonCls=}")

        def handleDerives(values):
            if isinstance(values, dict):
                values = [values]
            for val in (values or ()):  # Ensure derives getting build for each file referenced in this relation
                ensureDerived(val["dest"]["key"], prefix, self.derive, key)

        values = skel[boneName]
        if self.derive and values:
            if isinstance(values, dict) and "dest" not in values:  # multi lang
                for lang in values:
                    handleDerives(values[lang])
            else:
                handleDerives(values)

    def getReferencedBlobs(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> set[str]:
        r"""
        Retrieves the referenced blobs in the FileBone.

        :param SkeletonInstance skel: The skeleton instance this bone belongs to.
        :param str name: The name of the bone.
        :return: A set of download keys for the referenced blobs.
        :rtype: Set[str]

        This method iterates over the bone values for the given skeleton and bone name. It skips
        values that are None. For each non-None value, it adds the download key of the referenced
        blob to a set. Finally, it returns the set of unique download keys for the referenced blobs.
        """
        result = set()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            result.add(value["dest"]["dlkey"])
        return result

    def refresh(self, skel, boneName):
        r"""
        Refreshes the FileBone by recreating file entries if needed and importing blobs from ViUR 2.

        :param SkeletonInstance skel: The skeleton instance this bone belongs to.
        :param str boneName: The name of the bone.

        This method defines an inner function, recreateFileEntryIfNeeded(val), which is responsible
        for recreating the weak file entry referenced by the relation in val if it doesn't exist
        (e.g., if it was deleted by ViUR 2). It initializes a new skeleton for the "file" kind and
        checks if the file object already exists. If not, it recreates the file entry with the
        appropriate properties and saves it to the database.

        The main part of the refresh method calls the superclass's refresh method and checks if the
        configuration contains a ViUR 2 import blob source. If it does, it iterates through the file
        references in the bone value, imports the blobs from ViUR 2, and recreates the file entries if
        needed using the inner function.
        """
        super().refresh(skel, boneName)

        for _, _, value in self.iter_bone_value(skel, boneName):
            # Patch any empty serving_url when public file
            if (
                value
                and (value := value["dest"])
                and value["public"]
                and value["mimetype"]
                and value["mimetype"].startswith("image/")
                and not value["serving_url"]
            ):
                logging.info(f"Patching public image with empty serving_url {value['key']!r} ({value['name']!r})")
                try:
                    file_skel = value.read()
                except ValueError:
                    continue

                file_skel.patch(lambda skel: skel.refresh(), update_relations=False)
                value["serving_url"] = file_skel["serving_url"]

        # FIXME: REMOVE THIS WITH VIUR4
        if conf.viur2import_blobsource:
            from viur.core.modules.file import importBlobFromViur2
            from viur.core.skeleton import skeletonByKind

            def recreateFileEntryIfNeeded(val):
                # Recreate the (weak) filenetry referenced by the relation *val*. (ViUR2 might have deleted them)
                skel = skeletonByKind("file")()
                if skel.read(val["key"]):  # This file-object exist, no need to recreate it
                    return
                skel["key"] = val["key"]
                skel["name"] = val["name"]
                skel["mimetype"] = val["mimetype"]
                skel["dlkey"] = val["dlkey"]
                skel["size"] = val["size"]
                skel["width"] = val["width"]
                skel["height"] = val["height"]
                skel["weak"] = True
                skel["pending"] = False
                skel.write()

            # Just ensure the file get's imported as it may not have an file entry
            val = skel[boneName]
            if isinstance(val, list):
                for x in val:
                    importBlobFromViur2(x["dest"]["dlkey"], x["dest"]["name"])
                    recreateFileEntryIfNeeded(x["dest"])
            elif isinstance(val, dict):
                if not "dest" in val:
                    return
                importBlobFromViur2(val["dest"]["dlkey"], val["dest"]["name"])
                recreateFileEntryIfNeeded(val["dest"])

    def structure(self) -> dict:
        return super().structure() | {
            "valid_mime_types": self.validMimeTypes,
            "public": self.public,
        }

    def _atomic_dump(self, value) -> dict | None:
        value = super()._atomic_dump(value)
        if value is not None:
            value["dest"]["downloadUrl"] = conf.main_app.file.create_download_url(
                value["dest"]["dlkey"],
                value["dest"]["name"],
                derived=False,
                expires=conf.render_json_download_url_expiration
            )

        return value
