# -*- coding: utf-8 -*-
from server.bones import baseBone
from time import time
import HTMLParser, htmlentitydefs 
from server import db
from server.utils import markFileForDeletion
from server.config import conf
from google.appengine.api import search
from server.bones.stringBone import LanguageWrapper
import logging

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
					"td" : [ "colspan", "rowspan", "width", "height" ]+_attrsMargins+_attrsSpacing
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

	@staticmethod
	def generageSearchWidget(target,name="TEXT BONE",mode="equals"):
		return ( {"name":name,"mode":mode,"target":target,"type":"text"} )


	def __init__( self, validHtml=__undefinedC__, indexed=False, languages=None, *args, **kwargs ):
		baseBone.__init__( self,  *args, **kwargs )
		if indexed:
			raise NotImplementedError("indexed=True is not supported on textBones")
		if self.multiple:
			raise NotImplementedError("multiple=True is not supported on textBones")
		if validHtml==textBone.__undefinedC__:
			global _defaultTags
			validHtml = _defaultTags
		if not (languages is None or (isinstance( languages, list ) and len(languages)>0 and all( [isinstance(x,basestring) for x in languages] ))):
			raise ValueError("languages must be None or a list of strings ")
		self.languages = languages
		self.validHtml = validHtml
		if self.languages:
			self.value = LanguageWrapper( self.languages )

	def serialize( self, name, entity ):
		"""
			Fills this bone with user generated content

			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:param entity: An instance of the dictionary-like db.Entity class
			:type entity: :class:`server.db.Entity`
			:return: the modified :class:`server.db.Entity`
		"""
		if name == "key":
			return( entity )
		if self.languages:
			for k in entity.keys(): #Remove any old data
				if k.startswith("%s." % name ):
					del entity[ k ]
			for lang in self.languages:
				if lang in self.value.keys():
					val = self.value[ lang ]
					if not val or (not HtmlSerializer().santinize(val).strip() and not "<img " in val):
						#This text is empty (ie. it might contain only an empty <p> tag
						continue
					entity[ "%s.%s" % (name, lang) ] = val
		else:
			entity.set( name, self.value, self.indexed )
		return( entity )
		
	def unserialize( self, name, expando ):
		"""
			Inverse of serialize. Evaluates whats
			read from the datastore and populates
			this bone accordingly.

			:param name: The property-name this bone has in its Skeleton (not the description!)
			:type name: str
			:param expando: An instance of the dictionary-like db.Entity class
			:type expando: :class:`db.Entity`
		"""
		if not self.languages:
			if name in expando.keys():
				self.value = expando[ name ]
		else:
			self.value = LanguageWrapper( self.languages )
			for lang in self.languages:
				if "%s.%s" % ( name, lang ) in expando.keys():
					self.value[ lang ] = expando[ "%s.%s" % ( name, lang ) ]
			if not self.value.keys(): #Got nothing
				if name in expando.keys(): #Old (non-multi-lang) format
					self.value[ self.languages[0] ] = expando[ name ]
				for lang in self.languages:
					if not lang in self.value.keys() and "%s_%s" % ( name, lang ) in expando.keys():
						self.value[ lang ] = expando[ "%s_%s" % ( name, lang ) ]

		return( True )
	
	def fromClient( self, name, data ):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.
			
			:param name: Our name in the skeleton
			:type name: String
			:param data: *User-supplied* request-data
			:type data: Dict
			:returns: None or String
		"""
		if self.languages:
			self.value = LanguageWrapper( self.languages )
			for lang in self.languages:
				if "%s.%s" % (name,lang ) in data.keys():
					val = data[ "%s.%s" % (name,lang ) ]
					if not self.isInvalid( val ): #Returns None on success, error-str otherwise
						self.value[ lang ] = HtmlSerializer( self.validHtml ).santinize( val )
			if not any( self.value.values() ):
				return( "No / invalid values entered" )
			else:
				return( None )
		else:
			if name in data.keys():
				value = data[ name ]
			else:
				value = None
			if not value:
				self.value =""
				return( "No value entered" )
			if not isinstance( value, str ) and not isinstance( value, unicode ):
				value = unicode(value)
			err = self.isInvalid( value )
			if not err:
				self.value = HtmlSerializer( self.validHtml ).santinize( value )
				return( None )
			else:
				return( "Invalid value entered" )

	def getReferencedBlobs(self):
		"""
			Test for /file/download/ links inside our text body.
			Doesn't check for actual <a href=> or <img src=> yet.
		"""
		newFileKeys = []
		if self.languages:
			if self.value:
				for lng in self.languages:
					if lng in self.value.keys():
						val = self.value[ lng ]
						if not val:
							continue
						idx = val.find("/file/download/")
						while idx!=-1:
							idx += 15
							seperatorIdx = min( [ x for x in [val.find("/",idx), val.find("\"",idx)] if x!=-1] )
							fk = val[ idx:seperatorIdx]
							if not fk in newFileKeys:
								newFileKeys.append( fk )
							idx = val.find("/file/download/", seperatorIdx)
		else:
			if self.value:
				idx = self.value.find("/file/download/")
				while idx!=-1:
					idx += 15
					seperatorIdx = min( [ x for x in [self.value.find("/",idx), self.value.find("\"",idx)] if x!=-1] )
					fk = self.value[ idx:seperatorIdx]
					if not fk in newFileKeys:
						newFileKeys.append( fk )
					idx = self.value.find("/file/download/", seperatorIdx)
		return( newFileKeys )


	def getSearchTags(self):
		res = []
		if not self.value:
			return( res )
		if self.languages:
			for v in self.value.values():
				value = HtmlSerializer( None ).santinize( v.lower() )
				for line in unicode(value).splitlines():
					for key in line.split(" "):
						key = "".join( [ c for c in key if c.lower() in conf["viur.searchValidChars"]  ] )
						if key and key not in res and len(key)>3:
							res.append( key.lower() )
		else:
			value = HtmlSerializer( None ).santinize( self.value.lower() )
			for line in unicode(value).splitlines():
				for key in line.split(" "):
					key = "".join( [ c for c in key if c.lower() in conf["viur.searchValidChars"]  ] )
					if key and key not in res and len(key)>3:
						res.append( key.lower() )
		return( res )
		
	def getSearchDocumentFields(self, name):
		"""
			Returns a list of search-fields (GAE search API) for this bone.
		"""
		if self.languages:
			assert isinstance(self.value, dict), "The value shall already contain a dict, something is wrong here."

			if self.validHtml:
				return( [ search.HtmlField( name=name, value=unicode( self.value[lang] ), language=lang ) for lang in self.languages ] )
			else:
				return( [ search.TextField( name=name, value=unicode( self.value[lang] ), language=lang ) for lang in self.languages ] )
		else:
			if self.validHtml:
				return( [ search.HtmlField( name=name, value=unicode( self.value ) ) ] )
			else:
				return( [ search.TextField( name=name, value=unicode( self.value ) ) ] )
