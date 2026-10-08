"""
Actions: the standard endpoints of a :class:`viur.core.Module`, marked with ``@action``.

For an action ``edit`` the hooks are ``canEdit`` / ``onEdit`` / ``thenEdit`` / ``editSkel``; each one falls back
to the module's ``can`` / ``on`` / ``then`` / ``skel``. ``can`` is fail-closed, ``on`` and ``then`` do nothing.
Besides that naming rule, this module holds the vocabulary of the JSON response envelope.
"""
import dataclasses
import enum
import typing as t

__all__ = [
    "Datatype",
    "Status",
    "Step",
    "resolve_hook_names",
]


class Status(enum.StrEnum):
    """Outcome of an action, as reported by the JSON envelope."""

    INIT = "init"
    """Nothing written yet, e.g. an empty form."""

    CONTINUE = "continue"
    """A multi-step action is in progress; more steps follow."""

    SUCCESS = "success"
    """The action is completed and every write is done."""

    REJECTED = "rejected"
    """Stopped for a domain reason (validation, a forbidden transition); fix the input and retry."""

    ERROR = "error"
    """Stopped for a technical reason; the state is not as requested and a plain retry will not help."""


class Datatype(enum.StrEnum):
    """Shape of the envelope's ``data`` field."""

    ENTITY = "entity"
    LIST = "list"


@dataclasses.dataclass(slots=True)
class Step:
    """
    Presentation of one step of a multi-step action, carried in the envelope's ``steps`` map.

    :param icon: Icon name.
    :param icon_library: Icon set, e.g. ``"bootstrap"``.
    :param label: Human-readable label.
    :param url: Endpoint rendering this step, or ``None`` when it cannot be reached directly.
    """

    icon: str | None
    icon_library: str | None
    label: str | None
    url: str | None = None

    def to_dict(self) -> dict[str, t.Any]:
        return dataclasses.asdict(self)


def resolve_hook_names(action_name: str) -> tuple[str, str, str, str]:
    """
    The ``(can, on, then, skel)`` hook names of an action.

    ``snake_case`` actions become ``PascalCase`` in ``can``/``on``/``then`` and ``camelCase`` in the skel name.

    >>> resolve_hook_names("edit")
    ('canEdit', 'onEdit', 'thenEdit', 'editSkel')
    >>> resolve_hook_names("add_or_edit")
    ('canAddOrEdit', 'onAddOrEdit', 'thenAddOrEdit', 'addOrEditSkel')
    """
    pascal = "".join(segment[:1].upper() + segment[1:] for segment in action_name.split("_"))
    return f"can{pascal}", f"on{pascal}", f"then{pascal}", f"{pascal[:1].lower()}{pascal[1:]}Skel"
