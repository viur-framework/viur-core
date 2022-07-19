import json
from typing import Any

from ..utils import jinjaGlobalFilter
from ..default import Render


@jinjaGlobalFilter
def parseJSON(render: Render, value: str) -> Any:
    """
    Jinja2 filter: Parses a JSON-string into a python object.

    :param render: The html-renderer instance.
    :param value: The string to be parsed.
    :return: The parsed python object. \
                Returns None if no JSON could be parsed.
    """
    try:
        ret = json.loads(value)
    except ValueError:
        ret = None

    return ret
