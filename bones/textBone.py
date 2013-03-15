# -*- coding: utf-8 -*-
from server.bones import baseBone
from time import time
import HTMLParser, htmlentitydefs 
from server import db
from server.utils import markFileForDeletion
from server.config import conf
 

_attrsMargins = ["margin","margin-left","margin-right","margin-top","margin-bottom"]
_attrsSpacing = ["spacing","spacing-left","spacing-right","spacing-top","spacing-bottom"]
_attrsDescr = ["title","alt"]
_defaultTags = {
	"validTags": [	'font','b', 'a', 'i', 'u', 'span', 'div','p', 'img', 'ol', 'ul','li','acronym', #List of HTML-Tags which are valid
				'h1','h2','h3','h4','h5','h6', 'table', 'tr', 'td', 'th', 'br', 'hr', 'strong'], 
	"validAttrs": {	"font": ["color"], #Mapping of valid parameters for each tag (if a tag is not listed here: no parameters allowed)
					"a": ["href","target"]+_attrsDescr,
					"acronym": ["title"],
					"div": ["align","width","height"]+_attrsMargins+_attrsSpacing,
					"p":["align","width","height"]+_attrsMargins+_attrsSpacing,
					"span":["align","width","height"]+_attrsMargins+_attrsSpacing,
					"img":[ "src","target", "width","height", "align" ]+_attrsDescr+_attrsMargins+_attrsSpacing,
					"table": [ "width","align", "border", "cellspacing", "cellpadding" ]+_attrsDescr,
					"td" : [ "cellspan", "rowspan", "width", "heigt" ]+_attrsMargins+_attrsSpacing
				}, 
	"validStyles": ["font-weight","font-style","text-decoration","color", "display"], #List of CSS-Directives we allow
	"singleTags": ["br","img", "hr"] # List of tags, which dont have a corresponding end tag
}
del _attrsDescr, _attrsSpacing, _attrsMargins

class HtmlSerializer( HTMLParser.HTMLParser ): #html.parser.HTMLParser
	def __init__(self, validHtml=None ):
		global _defaultTags
		HTMLParser.HTMLParser.__init__(self)
		self.result = ""
		self.openTagsList = [] 
		self.validHtml = validHtml

	def handle_data(self, data):
		if data:
			self.result += data

	def handle_charref(self, name):
		self.result += "&#%s;" % ( name )

	def handle_entityref(self, name): #FIXME
		if name in htmlentitydefs.entitydefs.keys(): 
			self.result += "&%s;" % ( name )

	def handle_starttag(self, tag, attrs):
		""" Delete all tags except for legal ones """
		if self.validHtml and tag in self.validHtml["validTags"]:
			self.result = self.result + '<' + tag
			for k, v in attrs:
				if not tag in self.validHtml["validAttrs"].keys() or not k in self.validHtml["validAttrs"][ tag ]:
					continue					
				if k.lower()[0:2] != 'on' and v.lower()[0:10] != 'javascript':
					self.result = '%s %s="%s"' % (self.result, k, v)
			if "style" in [ k for (k,v) in attrs ]:
				syleRes = {}
				styles = [ v for (k,v) in attrs if k=="style"][0].split(";")
				for s in styles:
					style = s[ : s.find(":") ].strip()
					value = s[ s.find(":")+1 : ].strip()
					if style in self.validHtml["validStyles"] and not any( [(x in value) for x in ["\"",":",";"]] ):
						syleRes[ style ] = value
				if len( syleRes.keys() ):
					self.result += " style=\"%s\"" % "; ".join( [("%s: %s" % (k,v)) for (k,v) in syleRes.items()] )
			if tag in self.validHtml["singleTags"]:
				self.result = self.result + ' />'
			else:
				self.result = self.result + '>'
				self.openTagsList.insert( 0, tag)    

	def handle_endtag(self, tag):
		if self.validHtml and tag in self.openTagsList:
			for endTag in self.openTagsList[ : ]: #Close all currently open Tags until we reach the current one
				self.result = "%s</%s>" % (self.result, endTag)
				self.openTagsList.remove( endTag)
				if endTag==tag:
					break

	def cleanup(self): #FIXME: vertauschte tags
		""" Append missing closing tags """
		for tag in self.openTagsList:
			endTag = '</%s>' % tag
			self.result += endTag 
	
	def santinize( self, instr ):
		self.result = ""
		self.openTagsList = [] 
		self.feed( instr )
		self.close()
		self.cleanup()
		return( self.result )



class textBone( baseBone ):
	class __undefinedC__:
		pass

	type = "text"

	def __init__( self, validHtml=__undefinedC__, *args, **kwargs ):
		baseBone.__init__( self,  *args, **kwargs )
		if validHtml==textBone.__undefinedC__:
			global _defaultTags
			validHtml = _defaultTags
		self.validHtml = validHtml

	def serialize( self, name ):
		if name == "id":
			return( { } )
		else:
			return( {name:  self.value } )
	
	def fromClient( self, value ):
		if not value:
			self.value =""
			return( "No value entered" )
		if not isinstance( value, str ) and not isinstance( value, unicode ):
			value = unicode(value)
		err = self.canUse( value )
		if not err:
			self.value = HtmlSerializer( self.validHtml ).santinize( value )
			return( None )
		else:
			return( "Invalid value entered" )


	def postSavedHandler( self, key, skel, id, dbfields ):
		lockInfo = "textBone/%s" % ( key )
		oldFiles = db.Query( "file" ).ancestor( db.Key( str(id) )).filter( "lockinfo =",  lockInfo ).run(100)
		newFileKeys = []
		if not self.value:
			return
		idx = self.value.find("/file/view/")
		while idx!=-1:
			idx += 11
			seperatorIdx = min( [ x for x in [self.value.find("/",idx), self.value.find("\"",idx)] if x!=-1] )
			fk = self.value[ idx:seperatorIdx]
			if not fk in newFileKeys:
				newFileKeys.append( fk )
			idx = self.value.find("/file/view/", seperatorIdx)
		oldFileKeys = [ x["dlkey"] for x in oldFiles ]
		for newFileKey in [ x for x in newFileKeys if not x in oldFileKeys]:
			f = db.Entity( "file", parent=db.Key( str(id) ) )
			f["lockinfo"] = lockInfo
			f["dlkey"] = newFileKey
			f["weak"] = False
			db.Put( f )
		for oldFile in [ x for x in oldFiles if not x["dlkey"] in newFileKeys ]:
			markFileForDeletion( oldFile["dlkey"] )
			db.Delete( oldFile.key() )

	def postDeletedHandler( self, skel, key, id ):
		files = db.Query( "file").ancestor( db.Key( id ) ).run()
		for f in files:
			markFileForDeletion( f["dlkey"] )
			db.Delete( f.key() )

	def getTags(self):
		res = []
		if not self.value:
			return( res )
		value = HtmlSerializer( None ).santinize( self.value.lower() )
		for line in unicode(value).splitlines():
			for key in line.split(" "):
				key = "".join( [ c for c in key if c.lower() in conf["viur.searchValidChars"]  ] )
				if key and key not in res and len(key)>3:
					res.append( key.lower() )
		return( res )
