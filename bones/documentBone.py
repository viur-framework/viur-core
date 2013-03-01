from server.bones import textBone
from server.bones.textBone import HtmlSerializer 
import json

class ExtensionParser( HtmlSerializer ):
	"""
	Extended Html-Serializer
	Parses <!-- ext: comments and Inserts the parsed content
	"""
	
	def __init__(self, extensions=False, *args, **kwargs ):
		HtmlSerializer.__init__( self, *args, **kwargs )
		self.extensions = extensions
	
	def handle_comment(self, txt ):
		if self.extensions and txt.strip().upper().startswith( "EXT:" ):
			txt = txt.strip()
			extName = txt[ 4 : txt.find(" ") ]
			jsonData = txt[ txt.find(" ")+1 : ]
			data = json.loads( jsonData )
			for ext in self.extensions:
				if ext.name == extName:
					self.result += "<!-- Begin: %s -->" % extName
					self.result += ext.render( **data )
					self.result += "<!-- End: %s -->" % extName
		else:
			self.result += "<!--%s-->" % txt


class documentBone( textBone ):
	type = "document"
	
	def __init__(self, extensions=[], *args, **kwargs ):
		super( documentBone, self ).__init__( *args, **kwargs )
		self.extensions = extensions
		self.cache = ""

	def serialize( self, name ):
		return( {	"%s" % name: self.value, 
					"%s-cache" % name: self.cache } )
	
	def unserialize( self, name, expando ):
		self.value = None
		if name in expando.keys() \
			and "%s-cache" % name in expando.keys():
				self.value = expando[ name ]
				self.cache = expando[ "%s-cache" % name ]
		elif name in expando.keys():
			self.value = expando[ name ]
			self.cache = expando[ name ] #FIXME: ???
		return( True )

	def fromClient( self, value ):
		if not value:
			self.value = ""
			self.cache = ""
			return( "No value entered" )
		if not isinstance( value, str ) and not isinstance( value, unicode ):
			value = unicode(value)
		err = self.canUse( value )
		if not err:
			self.value = ExtensionParser( self.extensions, self.validHtml ).santinize( value )
			self.cache = self.processDocument( self.value )
			return( None )
		else:
			return( "Invalid value entered" )
	
	def processDocument(self, value ):
		"""Processes a Document and returns the resulting html
		@param value: Document to process
		@type value: string
		@returns: string
		"""
		res = ExtensionParser( self.extensions, self.validHtml ).santinize( value )
		return( res )

