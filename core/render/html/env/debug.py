# -*- coding: utf-8 -*-
import pprint
from logging import critical, debug, error, info, warning
from typing import Any

from viur.core.render.html.utils import jinjaGlobalFunction


@jinjaGlobalFunction
def logging(render, msg: str, level: str = "info", *args, **kwargs):
	"""
	Jinja2 global: Write log-level entry.
	The function shall be used for debug and tracing purposes.

	:param msg: Message to be delivered into logging.

	:param level: Logging level. This can either be "info" (default), "debug", "warning", "error" or "critical".
	"""

	level = level.lower()

	if level == "critical":
		critical(msg, *args, **kwargs)
	elif level == "error":
		error(msg, *args, **kwargs)
	elif level == "warning":
		warning(msg, *args, **kwargs)
	elif level == "debug":
		debug(msg, *args, **kwargs)
	else:
		info(msg, *args, **kwargs)


@jinjaGlobalFunction
def pprint(render, obj: Any) -> str:
	"""
	Jinja2 global: Provides a pprint function that renders into HTML.
	The function shall be used for debug purposes.

	:param obj: Object to be pprinted.
	:return: HTML-enabled pprint output.
	"""
	return pprint.pformat(obj).replace("\n", "<br>").replace(" ", "&nbsp;")
