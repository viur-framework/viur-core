from default import Render as default_render
from server.render.jinja2 import  user as user_default

class Render (default_render,user_default):
	pass
	
