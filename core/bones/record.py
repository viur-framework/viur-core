from viur.core.bones.base import BaseBone, getSystemInitialized, ReadFromClientError, ReadFromClientErrorSeverity
from typing import List, Union
import copy, logging


try:
    import extjson
except ImportError:
    # FIXME: That json will not read datetime objects
    import json as extjson


class RecordBone(BaseBone):
    type = "record"

    def __init__(
        self,
        *,
        format: str = None,
        indexed: bool = False,
        using: 'viur.core.skeleton.RelSkel' = None,
        **kwargs
    ):
        from viur.core.skeleton import RelSkel
        if not issubclass(using, RelSkel):
            raise ValueError("RecordBone requires for valid using-parameter (subclass of viur.core.skeleton.RelSkel)")

        super().__init__(indexed=indexed, **kwargs)
        self.using = using
        self.format = format
        if not format or indexed:
            raise NotImplementedError("A RecordBone must not be indexed and must have a format set")

    def singleValueUnserialize(self, val):
        if isinstance(val, str):
            try:
                value = extjson.loads(val)
            except:
                value = None
        else:
            value = val
        if not value:
            return None
        elif isinstance(value, list) and value:
            value = value[0]
        assert isinstance(value, dict), "Read something from the datastore thats not a dict: %s" % str(type(value))
        usingSkel = self.using()
        usingSkel.unserialize(value)
        return usingSkel

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        if not value:
            return value

        return value.serialize(parentIndexed=False)

    def parseSubfieldsFromClient(self) -> bool:
        """
        Whenever this request should try to parse subfields submitted from the client.
        Set only to true if you expect a list of dicts to be transmitted
        """
        return True

    def singleValueFromClient(self, value, skel, name, origData):
        usingSkel = self.using()
        if not usingSkel.fromClient(value, not (self.required or self.multiple)):
            usingSkel.errors.append(
                ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Incomplete data")
            )
        return usingSkel, usingSkel.errors

    def getSearchTags(self, values, key):
        def getValues(res, skel, valuesCache):
            for k, bone in skel.items():
                if bone.searchable:
                    for tag in bone.getSearchTags(valuesCache, k):
                        if tag not in res:
                            res.append(tag)
            return res

        value = values[key]
        res = []

        if not value:
            return res

        uskel = self.using()

        if self.multiple:
            for entry in value:
                res = getValues(res, uskel, entry)
        else:
            res = getValues(res, uskel, value)

        return res

    def getSearchDocumentFields(self, valuesCache, name, prefix=""):
        def getValues(res, skel, valuesCache, searchPrefix):
            for key, bone in skel.items():
                if bone.searchable:
                    res.extend(bone.getSearchDocumentFields(valuesCache, key, prefix=searchPrefix))

        value = valuesCache.get(name)
        res = []

        if not value:
            return res
        uskel = self.using()
        for idx, val in enumerate(value):
            getValues(res, uskel, val, "%s%s_%s" % (prefix, name, str(idx)))

        return res

    def getReferencedBlobs(self, skel, name):
        def blobsFromSkel(relSkel, valuesCache):
            blobList = set()
            for key, _bone in relSkel.items():
                blobList.update(_bone.getReferencedBlobs(relSkel, key))
            return blobList

        res = set()
        value = skel[name]

        if not value:
            return res
        uskel = self.using()
        if isinstance(value, list):
            for val in value:
                res.update(blobsFromSkel(uskel, val))

        elif isinstance(value, dict):
            res.update(blobsFromSkel(uskel, value))

        return res

    def getUniquePropertyIndexValues(self, valuesCache: dict, name: str) -> List[str]:
        """
            This is intentionally not defined as we don't now how to derive a key from the relskel
            being using (ie. which Fields to include and how).

        """
        raise NotImplementedError
