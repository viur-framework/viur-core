# -*- coding: utf-8 -*-
from server import  errors

class Site( object ):
	adminInfo = None

	def __init__(self, *args, **kwargs):
		super( Site, self ).__init__()

	def index( self,template="index",*arg,**kwargs ):
		if ".." in template or "/" in template:
			return
		try:
			template = self.render.getEnv().get_template( self.render.getTemplateFileName( "sites/"+template ) )
		except:
			raise errors.NotFound()
		return( template.render( ) )
	index.exposed = True	
	
Site.jinja2 = True
Site.vi = True
