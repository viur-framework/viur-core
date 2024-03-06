"""
The FileBone is a subclass of the TreeLeafBone class, which is a relational bone that can reference
another entity's fields. FileBone provides additional file-specific properties and methods, such as
managing file derivatives, handling file size and mime type restrictions, and refreshing file
metadata.
"""

from hashlib import sha256
from time import time
import typing as t
from viur.core import conf, db
from viur.core.bones.treeleaf import TreeLeafBone
from viur.core.tasks import CallDeferred

import logging


@CallDeferred
def ensureDerived(key: db.Key, srcKey, deriveMap: dict[str, t.Any], refreshKey: db.Key = None):
    r"""
    The function is a deferred function that ensures all pending thumbnails or other derived files
    are built. It takes the following parameters:

    :param db.key key: The database key of the file-object that needs to have its derivation map
        updated.
    :param str srcKey: A prefix for a stable key to prevent rebuilding derived files repeatedly.
    :param dict[str,Any] deriveMap: A list of DeriveDicts that need to be built or updated.
    :param db.Key refreshKey: If set, the function fetches and refreshes the skeleton after
        building new derived files.

    The function works by fetching the skeleton of the file-object, checking if it has any derived
    files, and updating the derivation map accordingly. It iterates through the deriveMap items and
    calls the appropriate deriver function. If the deriver function returns a result, the function
    creates a new or updated resultDict and merges it into the file-object's metadata. Finally,
    the updated results are written back to the database and the updateRelations function is called
    to ensure proper relations are maintained.
    """
    from viur.core.skeleton import skeletonByKind, updateRelations
    deriveFuncMap = conf.file_derivations
    skel = skeletonByKind("file")()
    if not skel.fromDB(key):
        logging.info("File-Entry went missing in ensureDerived")
        return
    if not skel["derived"]:
        logging.info("No Derives for this file")
        skel["derived"] = {}
    skel["derived"]["deriveStatus"] = skel["derived"].get("deriveStatus") or {}
    skel["derived"]["files"] = skel["derived"].get("files") or {}
    resDict = {}  # Will contain new or updated resultDicts that will be merged into our file
    for calleeKey, params in deriveMap.items():
        fullSrcKey = f"{srcKey}_{calleeKey}"
        paramsHash = sha256(str(params).encode("UTF-8")).hexdigest()  # Hash over given params (dict?)
        if skel["derived"]["deriveStatus"].get(fullSrcKey) != paramsHash:
            if calleeKey not in deriveFuncMap:
                logging.warning(f"File-Deriver {calleeKey} not found - skipping!")
                continue
            callee = deriveFuncMap[calleeKey]
            callRes = callee(skel, skel["derived"]["files"], params)
            if callRes:
                assert isinstance(callRes, list), "Old (non-list) return value from deriveFunc"
                resDict[fullSrcKey] = {"version": paramsHash, "files": {}}
                for fileName, size, mimetype, customData in callRes:
                    resDict[fullSrcKey]["files"][fileName] = {
                        "size": size,
                        "mimetype": mimetype,
                        "customData": customData
                    }

    def updateTxn(key, resDict):
        obj = db.Get(key)
        if not obj:  # File-object got deleted during building of our derives
            return
        obj["derived"] = obj.get("derived") or {}
        obj["derived"]["deriveStatus"] = obj["derived"].get("deriveStatus") or {}
        obj["derived"]["files"] = obj["derived"].get("files") or {}
        for k, v in resDict.items():
            obj["derived"]["deriveStatus"][k] = v["version"]
            for fileName, fileDict in v["files"].items():
                obj["derived"]["files"][fileName] = fileDict
        db.Put(obj)

    if resDict:  # Write updated results back and queue updateRelationsTask
        db.RunInTransaction(updateTxn, key, resDict)
        # Queue that updateRelations call at least 30 seconds into the future, so that other ensureDerived calls from
        # the same FileBone have the chance to finish, otherwise that updateRelations Task will call postSavedHandler
        # on that FileBone again - re-queueing any ensureDerivedCalls that have not finished yet.
        updateRelations(key, time() + 1, "derived", _countdown=30)
        if refreshKey:
            def refreshTxn():
                skel = skeletonByKind(refreshKey.kind)()
                if not skel.fromDB(refreshKey):
                    return
                skel.refresh()
                skel.toDB(update_relations=False)

            db.RunInTransaction(refreshTxn)


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
        refKeys: t.Optional[t.Iterable[str]] = ("name", "mimetype", "size", "width", "height", "derived"),
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

        def handleDerives(values):
            if isinstance(values, dict):
                values = [values]
            for val in values:  # Ensure derives getting build for each file referenced in this relation
                ensureDerived(val["dest"]["key"], f"{skel.kindName}_{boneName}", self.derive)

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
        from viur.core.skeleton import skeletonByKind

        def recreateFileEntryIfNeeded(val):
            # Recreate the (weak) filenetry referenced by the relation *val*. (ViUR2 might have deleted them)
            skel = skeletonByKind("file")()
            if skel.fromDB(val["key"]):  # This file-object exist, no need to recreate it
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
            k = skel.toDB()

        from viur.core.modules.file import importBlobFromViur2
        super().refresh(skel, boneName)
        if conf.viur2import_blobsource:
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
            "valid_mime_types": self.validMimeTypes
        }
