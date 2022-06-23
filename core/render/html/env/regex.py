import re
from typing import Optional

from viur.core.render.html.utils import jinjaGlobalFunction
from ..default import Render


@jinjaGlobalFunction
def regexMatch(render: Render, pattern: str, string: str, flags: int = 0) -> re.Match:
    """
    Jinja2 global: Match a string for regular expression pattern.
    This function internally runs re.match().

    :param render: The html-renderer instance.
    :param pattern: Regular expression pattern to be matched.
    :param string: String where to be searched in.
    :param flags: Flags to be passed to re.search().

    :return: A matching object on success, else None.
    """
    return re.match(pattern, string, flags)


@jinjaGlobalFunction
def regexReplace(render: Render, string: str, pattern: str, replace: str) -> str:
    """
    Jinja2 global: Replace string by regular expression pattern.

    :param render: The html-renderer instance.
    :param string: String to be replaced.
    :param pattern: Regular expression pattern to be matched.
    :param replace: Replacement string to be inserted for every matching pattern.

    :return: The string with the replaced matches.
    """
    return re.sub(pattern, replace, string)


@jinjaGlobalFunction
def regexSearch(render: Render, string: str, pattern: str, flags=0) -> Optional[re.Match]:
    """
    Jinja2 global: Search a string for regular expression pattern.
    This function internally runs re.search().

    :param render: The html-renderer instance.
    :param string: String where to be searched in.
    :param pattern: Regular expression pattern to be matched.
    :param flags: Flags to be passed to re.search().

    :return: A matching object on success, else None.
    """
    return re.search(pattern, string, flags)
