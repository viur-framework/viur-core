import json
import typing as t
from enum import Enum
from viur.core import db, current
from viur.core.render.abstract import AbstractRenderer
from viur.core.skeleton import SkeletonInstance, SkelList
from viur.core.i18n import translate
from viur.core.config import conf
from datetime import datetime


class CustomJsonEncoder(json.JSONEncoder):
    """
        This custom JSON-Encoder for this json-render ensures that translations are evaluated and can be dumped.
    """

    def default(self, o: t.Any) -> t.Any:

        if isinstance(o, translate):
            return str(o)
        elif isinstance(o, datetime):
            return o.isoformat()
        elif isinstance(o, db.Key):
            return str(o)
        elif isinstance(o, Enum):
            return o.value
        elif isinstance(o, set):
            return tuple(o)
        elif isinstance(o, SkeletonInstance):
            return {bone_name: o[bone_name] for bone_name in o}
        return json.JSONEncoder.default(self, o)


class DefaultRender(AbstractRenderer):
    kind = "json"

    @staticmethod
    def render_structure(structure: dict):
        """
        Performs structure rewriting according to VIUR2/3 compatibility flags.
        # fixme: Remove this entire function with VIUR4
        """
        for struct in structure.values():
            # Optionally replace new-key by a copy of the value under the old-key
            if "json.bone.structure.camelcasenames" in conf.compatibility:
                for find, replace in {
                    "boundslat": "boundsLat",
                    "boundslng": "boundsLng",
                    "emptyvalue": "emptyValue",
                    "max": "maxAmount",
                    "maxlength": "maxLength",
                    "min": "minAmount",
                    "preventduplicates": "preventDuplicates",
                    "readonly": "readOnly",
                    "valid_html": "validHtml",
                    "valid_mime_types": "validMimeTypes",
                }.items():
                    if find in struct:
                        struct[replace] = struct[find]

            # Call render_structure() recursively on "using" and "relskel" members.
            for substruct in ("using", "relskel"):
                if substruct in struct and struct[substruct]:
                    struct[substruct] = DefaultRender.render_structure(struct[substruct])

        # Optionally return list of tuples instead of dict
        if "json.bone.structure.keytuples" in conf.compatibility:
            return [(key, struct) for key, struct in structure.items()]

        return structure

    def renderEntry(self, skel: SkeletonInstance, actionName, params=None):

        structure = None
        errors = None

        if isinstance(skel, list):
            raise ValueError("renderEntry cannot handle lists")

        elif isinstance(skel, SkeletonInstance):
            vals = skel.dump()
            structure = DefaultRender.render_structure(skel.structure())
            errors = [{"severity": x.severity.value, "fieldPath": x.fieldPath, "errorMessage": x.errorMessage,
                       "invalidatedFields": x.invalidatedFields} for x in skel.errors]

        else:  # Hopefully we can pass it directly...
            vals = skel

        res = {
            "action": actionName,
            "errors": errors,
            "params": params,
            "structure": structure,
            "values": vals,
        }

        current.request.get().response.headers["Content-Type"] = "application/json"
        return json.dumps(res, cls=CustomJsonEncoder)

    def view(self, skel: SkeletonInstance, action: str = "view", params=None, **kwargs):
        return self.renderEntry(skel, action, params)

    def list(self, skellist: SkelList, action: str = "list", params=None, **kwargs):

        # Rendering the structure in lists is flagged as deprecated
        structure = None
        cursor = None
        orders = None

        if skellist:
            if isinstance(skellist[0], SkeletonInstance):
                if "json.bone.structure.inlists" in conf.compatibility:
                    structure = DefaultRender.render_structure(skellist[0].structure())

                cursor = skellist.getCursor()
                orders = skellist.get_orders()

            skellist = [item.dump() for item in skellist]
        else:
            skellist = []

        # VIUR4 ;-)
        # loc = locals()
        # res = {k: loc[k] for k in ("action", "cursor", "params", "skellist", "structure", "orders") if loc[k]}

        res = {
            "action": action,
            "cursor": cursor,
            "params": params,
            "skellist": skellist,
            "structure": structure,
            "orders": orders
        }

        current.request.get().response.headers["Content-Type"] = "application/json"
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
        current.request.get().response.headers["Content-Type"] = "application/json"
        return json.dumps(rootNodes, cls=CustomJsonEncoder)

    def render(self, action: str, skel: t.Optional[SkeletonInstance] = None, **kwargs):
        """
        Universal rendering function.

        Handles an action and a skeleton. It shall be used by any action, in future.
        """
        return self.renderEntry(skel, action, params=kwargs)
