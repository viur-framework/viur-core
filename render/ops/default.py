from server.render.jinja2 import default
from server import bones, utils, request, session, conf, errors
import os

class Render( default ):
	#htmlpath = "server/template/ops"

	def getTemplateFileName( self, template, ignoreStyle=False ):
		validChars = "abcdefghijklmnopqrstuvwxyz1234567890-"
		if "htmlpath" in dir( self ):
			htmlpath = self.htmlpath
		else:
			htmlpath = "html"
		if not ignoreStyle\
			and "style" in list( request.current.get().kwargs.keys())\
			and all( [ x in validChars for x in request.current.get().kwargs["style"].lower() ] ):
				stylePostfix = "_"+request.current.get().kwargs["style"]
		else:
			stylePostfix = ""
		lang = session.current.getLanguage()
		fnames = [ template+stylePostfix+".html", template+".html" ]
		if lang:
			fnames = [ 	os.path.join(  lang, template+stylePostfix+".html"),
						template+stylePostfix+".html",
						os.path.join(  lang, template+".html"),
						template+".html" ]
		for fn in fnames: #Check the templatefolder of the application
			if os.path.isfile( os.path.join( os.getcwd(), htmlpath, "ops", fn ) ):
				return( "ops/"+fn )
		for fn in fnames: #Check the fallback
			if os.path.isfile( os.path.join( os.getcwd(), "server", "template", "ops", fn ) ):
				return( "ops/"+fn )
		raise errors.NotFound( "Template %s not found." % template )

