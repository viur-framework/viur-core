import json
from collections import OrderedDict
from enum import Enum

from viur.core import bones, utils, config, db
from viur.core.skeleton import SkeletonInstance
from viur.core.utils import currentRequest
from viur.core.i18n import translate
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union


class CustomJsonEncoder(json.JSONEncoder):
    """
        This custom JSON-Encoder for this json-render ensures that translations are evaluated and can be dumped.
    """

    def default(self, o: Any) -> Any:
        if isinstance(o, translate):
            return str(o)
        elif isinstance(o, datetime):
            return o.isoformat()
        elif isinstance(o, db.Key):
            return db.encodeKey(o)
        elif isinstance(o, Enum):
            return o.value
        return json.JSONEncoder.default(self, o)


class DefaultRender(object):
    kind = "json"

    def __init__(self, parent=None, *args, **kwargs):
        super(DefaultRender, self).__init__(*args, **kwargs)
        self.parent = parent


    def renderSingleBoneValue(self, value: Any,
                              bone: bones.BaseBone,
                              skel: SkeletonInstance,
                              key
                              ) -> Union[Dict, str, None]:
        """
        Renders the value of a bone.

        It can be overridden and super-called from a custom renderer.

        :param bone: The bone which value should be rendered.
        :type bone: Any bone that inherits from :class:`server.bones.base.BaseBone`.

        :return: A dict containing the rendered attributes.
        """
        if isinstance(bone, bones.RelationalBone):
            if isinstance(value, dict):
                return {
                    "dest": self.renderSkelValues(value["dest"], injectDownloadURL=isinstance(bone, bones.FileBone)),
                    "rel": (self.renderSkelValues(value["rel"], injectDownloadURL=isinstance(bone, bones.FileBone))
                            if value["rel"] else None),
                }
        elif isinstance(bone, bones.RecordBone):
            return self.renderSkelValues(value)
        elif isinstance(bone, bones.PasswordBone):
            return ""
        else:
            return value
        return None

    def renderBoneValue(self, bone: bones.BaseBone, skel: SkeletonInstance, key: str) -> Union[List, Dict, None]:
        boneVal = skel[key]
        if bone.languages and bone.multiple:
            res = {}
            for language in bone.languages:
                if boneVal and language in boneVal and boneVal[language]:
                    res[language] = [self.renderSingleBoneValue(v, bone, skel, key) for v in boneVal[language]]
                else:
                    res[language] = []
        elif bone.languages:
            res = {}
            for language in bone.languages:
                if boneVal and language in boneVal and boneVal[language]:
                    res[language] = self.renderSingleBoneValue(boneVal[language], bone, skel, key)
                else:
                    res[language] = None
        elif bone.multiple:
            res = [self.renderSingleBoneValue(v, bone, skel, key) for v in boneVal] if boneVal else None
        else:
            res = self.renderSingleBoneValue(boneVal, bone, skel, key)
        return res

    def renderSkelValues(self, skel: SkeletonInstance, injectDownloadURL: bool = False) -> Optional[Dict]:
        """
        Prepares values of one :class:`viur.core.skeleton.Skeleton` or a list of skeletons for output.

        :param skel: Skeleton which contents will be processed.
        """
        if skel is None:
            return None
        elif isinstance(skel, dict):
            return skel
        res = {}
        for key, bone in skel.items():
            res[key] = self.renderBoneValue(bone, skel, key)
        if injectDownloadURL and "dlkey" in skel and "name" in skel:
            res["downloadUrl"] = utils.downloadUrlFor(skel["dlkey"], skel["name"], derived=False,
                                                      expires=config.conf["viur.render.json.downloadUrlExpiration"])
        return res

    def renderEntry(self, skel: SkeletonInstance, actionName, params=None):
        if isinstance(skel, list):
            vals = [self.renderSkelValues(x) for x in skel]
            struct = skel[0].structure(render_type="json")
            errors = None
        elif isinstance(skel, SkeletonInstance):
            vals = self.renderSkelValues(skel)
            struct = skel.structure(render_type="json")
            errors = [{"severity": x.severity.value, "fieldPath": x.fieldPath, "errorMessage": x.errorMessage,
                       "invalidatedFields": x.invalidatedFields} for x in skel.errors]
        else:  # Hopefully we can pass it directly...
            vals = skel
            struct = None
            errors = None
        res = {
            "values": vals,
            "structure": struct,
            "errors": errors,
            "action": actionName,
            "params": params
        }
        currentRequest.get().response.headers["Content-Type"] = "application/json"
        return json.dumps(res, cls=CustomJsonEncoder)

    def view(self, skel: SkeletonInstance, action: str = "view", params=None, **kwargs):
        return self.renderEntry(skel, action, params)

    def list(self, skellist, action: str = "list", params=None, **kwargs):
        res = {}
        skels = []
        if skellist:
            for skel in skellist:
                skels.append(self.renderSkelValues(skel))

            res["cursor"] = skellist.getCursor()
            res["structure"] = skellist[0].structure(render_type="json")
        else:
            res["structure"] = None
            res["cursor"] = None

        res["skellist"] = skels
        res["action"] = action
        res["params"] = params
        res["orders"] = skellist.get_orders()


        currentRequest.get().response.headers["Content-Type"] = "application/json"
        return json.dumps(res, cls=CustomJsonEncoder)

    def add(self, skel: SkeletonInstance, action: str = "add", params=None, **kwargs):
        return self.renderEntry(skel, action, params)

    def edit(self, skel: SkeletonInstance, action: str = "edit", params=None, **kwargs):
        return self.renderEntry(skel, action, params)

    def editSuccess(self, skel: SkeletonInstance, action: str = "editSuccess", params=None, **kwargs):
        return self.renderEntry(skel, action, params)

    def addSuccess(self, skel: SkeletonInstance, action: str = "addSuccess", params=None, **kwargs):
        return self.renderEntry(skel, action, params)

    def deleteSuccess(self, skel: SkeletonInstance, params=None, *args, **kwargs):
        return json.dumps("OKAY")

    def listRootNodes(self, rootNodes, *args, **kwargs):
        for rn in rootNodes:
            rn["key"] = db.encodeKey(rn["key"])

        return json.dumps(rootNodes)
