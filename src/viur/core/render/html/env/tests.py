import typing as t

from ..default import Render
from ..utils import jinjaGlobalTest


@jinjaGlobalTest("dict")
def test_dict(render: Render, value: t.Any) -> bool:
    """Jinja2 test: Return True if the object is a dict."""
    return isinstance(value, dict)


@jinjaGlobalTest("list")
def test_list(render: Render, value: t.Any) -> bool:
    """Jinja2 test: Return True if the object is a list."""
    return isinstance(value, list)
