import json
import typing as t
from decimal import Decimal
from enum import Enum
from viur.core import current
from viur.core.actions import Datatype, Status, Step
from viur.core.bones.base import ReadFromClientError
from viur.core.render.abstract import AbstractRenderer
from viur.core.skeleton import SkeletonInstance, SkelList
from viur.core.i18n import translate
from viur.core.config import conf
from datetime import datetime

ENVELOPE_VERSION: t.Final[int] = 2
"""Version of the JSON response envelope, the first key of every response."""

_ENVELOPE_ARGUMENTS: t.Final[frozenset[str]] = frozenset({
    "next_url", "status", "step", "step_status", "steps", "follow", "errors",
})
"""Keyword arguments of the render verbs that reach the envelope; the HTML renderer's own ones (``tpl`` and
template variables) are dropped."""

_SUCCESS_SUFFIXES: t.Final[tuple[str, ...]] = ("Success", "_success")
"""A render action with one of these suffixes (``editSuccess``, ``login_success``) reports a completed operation,
under its name without the suffix."""


def _envelope_arguments(kwargs: dict) -> dict:
    """The keyword arguments of a render call that the envelope understands."""
    return {key: value for key, value in kwargs.items() if key in _ENVELOPE_ARGUMENTS}


# VIUR4: Remove this piece of sh..
class CustomJsonEncoder(json.JSONEncoder):
    """
        This custom JSON-Encoder for this json-render ensures that translations are evaluated and can be dumped.
    """

    def default(self, o: t.Any) -> t.Any:

        if isinstance(o, Decimal):
            return str(o)
        elif isinstance(o, translate):
            return str(o)
        elif isinstance(o, datetime):
            return o.isoformat()
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
        #FIXME: Remove this entire function with VIUR4
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

    def renderEntry(
        self,
        skel: t.Any,
        actionName: str,
        params: t.Any = None,
        *,
        next_url: str | None = None,
        status: Status | None = None,
        step: str | None = None,
        step_status: Status | None = None,
        steps: dict[str, Step | dict] | None = None,
        follow: str | None = None,
        errors: list[ReadFromClientError] | None = None,
    ) -> str:
        """
        Renders an entity envelope.

        A :class:`SkeletonInstance` (or anything with ``dump()`` and ``structure()``) contributes its values,
        structure and errors; any other payload becomes ``data`` as it is, without a structure.

        :param skel: The skeleton, or the payload of an action that has none.
        :param actionName: The render action; ``view`` and ``*Success``/``*_success`` report ``success``, a skeleton
            with errors ``rejected``, anything else ``init``.
        :param params: Unused; the envelope carries no parameters.
        :param next_url: Default for *follow*.
        :param status: Explicit status, instead of the one derived from *actionName* and the skeleton.
        :param step: Current step of a multi-step action.
        :param step_status: Outcome of that step.
        :param steps: All steps; defaults to the module's :meth:`viur.core.Module.steps`.
        :param follow: URL the client may navigate to next.
        :param errors: Explicit errors, instead of the skeleton's own.
        """
        is_success = actionName == "view" or actionName.endswith(_SUCCESS_SUFFIXES)
        verb = actionName.removesuffix(_SUCCESS_SUFFIXES[0]).removesuffix(_SUCCESS_SUFFIXES[1])
        is_renderable = callable(getattr(skel, "dump", None)) and callable(getattr(skel, "structure", None))

        if status is None:
            if is_success:
                status = Status.SUCCESS
            elif is_renderable and skel.errors:
                status = Status.REJECTED
            else:
                status = Status.INIT

        if errors is None:
            errors = skel.errors if is_renderable else []

        return self._envelope(
            action=verb,
            status=status,
            datatype=Datatype.LIST if isinstance(skel, (list, tuple)) else Datatype.ENTITY,
            structure=DefaultRender.render_structure(skel.structure()) if is_renderable else None,
            data=skel.dump() if is_renderable else skel,
            errors=errors,
            step=step,
            step_status=step_status,
            steps=steps,
            follow=follow if follow is not None else next_url,
        )

    def _envelope(
        self,
        *,
        action: str,
        status: Status,
        datatype: Datatype,
        data: t.Any,
        structure: dict | None = None,
        errors: t.Iterable[ReadFromClientError] = (),
        step: str | None = None,
        step_status: Status | None = None,
        steps: dict[str, Step | dict] | None = None,
        follow: str | None = None,
        cursor: str | None = None,
        orders: t.Iterable | None = None,
    ) -> str:
        """
        Dumps the response envelope: ``version``, ``action``, ``status``, ``step``, ``step_status``, ``steps``,
        ``follow``, ``datatype``, ``module``, ``structure``, ``data`` and ``errors``, plus ``meta`` with ``cursor``
        and ``orders`` for a list.
        """
        if steps is None and self.parent is not None:
            steps = self.parent.steps() or None

        envelope = {
            "version": ENVELOPE_VERSION,
            "action": current.action.get() or action,
            "status": status,
            "step": step,
            "step_status": step_status,
            "steps": {key: value.to_dict() if isinstance(value, Step) else value for key, value in steps.items()}
            if steps else None,
            "follow": follow,
            "datatype": datatype,
            "module": self.parent.moduleName if self.parent is not None else None,
            "structure": structure,
            "data": data,
            "errors": [
                {
                    "error": error.severity.name.upper(),
                    "errorMessage": error.errorMessage,
                    "fieldPath": error.fieldPath,
                    "invalidatedFields": error.invalidatedFields,
                    "severity": error.severity.value,
                }
                for error in errors
            ],
        }

        if datatype is Datatype.LIST:
            envelope["meta"] = {
                "cursor": cursor,
                "orders": [
                    order if isinstance(order, dict)
                    else {"field": order[0], "dir": "desc" if "desc" in str(order[1]).lower() else "asc"}
                    for order in orders or ()
                ],
            }

        current.request.get().response.headers["Content-Type"] = "application/json"
        return json.dumps(envelope, cls=CustomJsonEncoder)

    def view(self, skel: SkeletonInstance, action: str = "view", params=None, **kwargs):
        return self.renderEntry(skel, action, params, **_envelope_arguments(kwargs))

    def list(self, skellist: SkelList, action: str = "list", params=None, **kwargs):
        return self._envelope(
            action=action,
            status=kwargs.get("status") or Status.SUCCESS,
            datatype=Datatype.LIST,
            data=[skel.dump() for skel in skellist],
            steps=kwargs.get("steps"),
            follow=kwargs.get("follow"),
            cursor=skellist.getCursor() if skellist else None,
            orders=skellist.get_orders() if skellist else None,
        )

    def add(self, skel: SkeletonInstance, action: str = "add", params=None, **kwargs):
        return self.renderEntry(skel, action, params, **_envelope_arguments(kwargs))

    def edit(self, skel: SkeletonInstance, action: str = "edit", params=None, **kwargs):
        return self.renderEntry(skel, action, params, **_envelope_arguments(kwargs))

    def editSuccess(self, skel: SkeletonInstance, action: str = "editSuccess", params=None, **kwargs):
        return self.renderEntry(skel, action, params, **_envelope_arguments(kwargs))

    def addSuccess(self, skel: SkeletonInstance, action: str = "addSuccess", params=None, **kwargs):
        return self.renderEntry(skel, action, params, **_envelope_arguments(kwargs))

    def deleteSuccess(self, skel: SkeletonInstance, params=None, *args, **kwargs):
        # The deleted entry itself, so a client can offer undo or keep an audit trail.
        return self.renderEntry(skel, "deleteSuccess", params, **_envelope_arguments(kwargs))

    def listRootNodes(self, rootNodes, *args, **kwargs):
        return self._envelope(action="listRootNodes", status=Status.SUCCESS, datatype=Datatype.LIST, data=rootNodes)

    def render(
        self,
        action: str,
        skel: t.Optional[SkeletonInstance] = None,
        *,
        next_url: t.Optional[str] = None,
        **kwargs
    ):
        """
        Universal rendering function.

        Handles an action and a skeleton. It shall be used by any action, in future.
        """
        return self.renderEntry(skel, action, next_url=next_url, **_envelope_arguments(kwargs))
