import logging
from hashlib import sha256
from time import time
from typing import Any, Dict, List, Set, Union

from viur.core import conf, db
from viur.core.bones.treeleaf import TreeLeafBone
from viur.core.tasks import CallDeferred


@CallDeferred
def ensureDerived(key: db.Key, srcKey, deriveMap: Dict[str, Any], refreshKey: db.Key = None):
    """
    Ensure that pending thumbnails or other derived Files are build
    :param key: DB-Key of the file-object on which we should update the derivemap
    :param srcKey: Prefix for a (hopefully) stable key to prevent rebuilding derives over and over again
    :param deriveMap: List of DeriveDicts we should build/update
    :param refreshKey: If set, we'll fetch and refresh the skeleton after building new derives
    """
    from viur.core.skeleton import skeletonByKind, updateRelations
    deriveFuncMap = conf["viur.file.derivers"]
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
        fullSrcKey = "%s_%s" % (srcKey, calleeKey)
        paramsHash = sha256(str(params).encode("UTF-8")).hexdigest()  # Hash over given params (dict?)
        if skel["derived"]["deriveStatus"].get(fullSrcKey) != paramsHash:
            if calleeKey not in deriveFuncMap:
                logging.warning("File-Deriver %s not found - skipping!" % calleeKey)
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
                skel.toDB(clearUpdateTag=True)

            db.RunInTransaction(refreshTxn)


class FileBone(TreeLeafBone):
    kind = "file"
    type = "relational.tree.leaf.file"
    refKeys = ["name", "key", "mimetype", "dlkey", "size", "width", "height", "derived"]

    def __init__(
        self,
        *,
        derive: Union[None, Dict[str, Any]] = None,
        maxFileSize: Union[None, int] = None,
        validMimeTypes: Union[None, List[str]] = None,
        **kwargs
    ):
        """
        Initializes a new Filebone. All properties inherited by RelationalBone are supported.
        :param format: Hint for the UI how to display a file entry (defaults to it's filename)
        :param derive: A set of functions used to derive other files from the referenced ones. Used fe. to create
            thumbnails / images for srcmaps from hires uploads. If set, must be a dictionary from string (a key from
            conf["viur.file.derivers"]) to the parameters passed to that function. The parameters can be any type
            (including None) that can be json-serialized.

            Example:
                >>> derive = {"thumbnail": [{"width": 111}, {"width": 555, "height": 666}]}
        :param validMimeTypes: A list of Mimetypes that can be selected in this bone (or None for any).
            Wildcards ("image/*") are supported.

            Example:
                >>> validMimeTypes=["application/pdf", "image/*"]
        :param maxFileSize: The maximum filesize accepted by this bone in bytes. None means no limit. This will always
            be checked against the original file uploaded - not any of it's derivatives.
        """
        super().__init__(**kwargs)

        if "dlkey" not in self.refKeys:
            self.refKeys.append("dlkey")

        self.derive = derive
        self.validMimeTypes = validMimeTypes
        self.maxFileSize = maxFileSize

    def isInvalid(self, value):
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
        super().postSavedHandler(skel, boneName, key)

        def handleDerives(values):
            if isinstance(values, dict):
                values = [values]
            for val in values:  # Ensure derives getting build for each file referenced in this relation
                ensureDerived(val["dest"]["key"], "%s_%s" % (skel.kindName, boneName), self.derive)

        values = skel[boneName]
        if self.derive and values:
            if isinstance(values, dict) and "dest" not in values:  # multi lang
                for lang in values:
                    handleDerives(values[lang])
            else:
                handleDerives(values)

    def getReferencedBlobs(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> Set[str]:
        result = set()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            result.add(value["dest"]["dlkey"])
        return result

    def refresh(self, skel, boneName):
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
        if conf.get("viur.viur2import.blobsource"):
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
