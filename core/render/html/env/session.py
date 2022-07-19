from typing import Dict

from viur.core.render.html.utils import jinjaGlobalFunction
from viur.core.utils import currentSession
from ..default import Render


@jinjaGlobalFunction
def getSession(render: Render) -> Dict:
    """
    Jinja2 global: Allows templates to store variables server-side inside the session.

    Note: This is done in a separated part of the session for security reasons.

    :returns: A dictionary of session variables.
    """
    currSess = currentSession.get()
    if not currSess.get("JinjaSpace"):
        currSess["JinjaSpace"] = {}
    return currSess.get("JinjaSpace")


@jinjaGlobalFunction
def setSession(render: Render, name: str, value: str) -> None:
    """
    Jinja2 global: Allows templates to store variables on server-side inside the session.

    Note: This is done in a separated part of the session for security reasons.

    :param render: The html-renderer instance.
    :param name: Name of the key
    :param value: Value to store with name.
    """
    sessionData = getSession(render)
    sessionData[name] = value
    currSess = currentSession.get()
    currSess["JinjaSpace"] = sessionData
    currSess.markChanged()
