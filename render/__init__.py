import jinja2
import admin
import xml
import json
import rss
try:
	import pdf
except ImportError: #We miss some of our 3rd party modules
	pass
try:
	# The VI-Render will only be available if the "vi" folder is present
	import vi
except ImportError:
	import logging
	logging.error("VI NOT AVAIABLE")
	pass
