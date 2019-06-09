# -*- coding: utf-8 -*-
from . import html
from . import admin
from . import xml
from . import json

try:
	# The VI-Render will only be available if the "vi" folder is present
	import vi
except ImportError:
	import logging

	logging.error("VI NOT AVAILABLE")
	pass
