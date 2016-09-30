import html
import admin
import xml
import json

try:
	# The VI-Render will only be available if the "vi" folder is present
	import vi
except ImportError:
	import logging
	logging.error("VI NOT AVAIABLE")
	pass
