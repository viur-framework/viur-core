# -*- coding: utf-8 -*-
from server.render.jinja2.utils import jinjaGlobal
from datetime import datetime

@jinjaGlobal
def now():
	"""
	Jinja2 global: Returns the current date and time.

	:return: The current date & time.
	:rtype: datetime
	"""
	return datetime.now()
