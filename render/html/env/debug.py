# -*- coding: utf-8 -*-
from viur.server.render.html.utils import jinjaGlobalFunction, jinjaGlobalFilter
from logging import critical, error, warning, debug, info
import pprint


@jinjaGlobalFunction
def logging(render, msg, kind="info", **kwargs):
	"""
	Jinja2 global: Write log-level entry.
	The function shall be used for debug and tracing purposes.

	:param msg: Message to be delivered into logging.
	:type msg: str

	:param kind: Logging kind. This can either be "info" (default), "debug", "warning", "error" or "critical".
	:type kind: str
	"""

	kind = kind.lower()

	if kind == "critical":
		critical(msg, **kwargs)
	elif kind == "error":
		error(msg, **kwargs)
	elif kind == "warning":
		warning(msg, **kwargs)
	elif kind == "debug":
		debug(msg, **kwargs)
	else:
		info(msg, **kwargs)


@jinjaGlobalFunction
def pprint(render, obj):
	"""
	Jinja2 global: Provides a pprint function that renders into HTML.
	The function shall be used for debug purposes.

	:param obj: Object to be pprinted.
	:return: HTML-enabled pprint output.
	"""
	return pprint.pformat(obj).replace("\n", "<br>").replace(" ", "&nbsp;")
