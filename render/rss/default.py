# -*- coding: utf-8 -*-
import logging
from server import errors, request
from server.bones.textBone import HtmlSerializer
from string import Template
from datetime import datetime
import time
from email.Utils import formatdate


class DefaultRender( object ):
	"""
		This is a really simple render, providing data as RSS-Stream.
		Only list is supported.
		Each application must specify an "rssInfo" - dict, which gives this
		render additional information how the data should be formated.
		E.g.
			rssInfo = { 	"feed": {	"title": "My RSS Feed" , 
								"link": "http://www.example.com",
								"descr": "An example", 
								"lang": "en", 
								"author": "Me, Myself and I", 
								"date": datetime.now(),
								"image": {	"url":"https://example.com/image.jpg"
											"title":"My RSS Feed",
											"link":"https://example.com/"}
								}
							},
						"item": {	"title": lambda skel: skel.name.value, 
								"descr": lambda skel: skel.descr.value[ : 255], 
								"link": lambda skel: "http://www.tws.de/calender/view/%s" % skel.id.value, 
								"id": lambda skel: skel.id.value, 
								"date": lambda skel: skel.creationdate.value
								}
			}
		Each value can be eiter a string, any callable taking no arguments in "feed" and one argument (the skeleton) in "item", or a datetime object.
		Its possible to return datetime-objects from the callable.
		Each key in "feed" and "item" can be missing (it will be filled with default values), however the structure rssInfo = { "feed": {},"item": {} } must be present.
	"""
	
	preamble = Template("""
<?xml version="1.0" encoding="utf-8"?>
	<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
	<channel>
		<title>${title}</title>
		<link>${link}</link>
		<description>${descr}</description>
		<language>${lang}</language>
		<copyright>${author}</copyright>
		<pubDate>${date}</pubDate>
		${image}
		<atom:link href="${feedurl}" rel="self" type="application/rss+xml" />
""")
	
	item = Template("""
		<item>
			<title>${title}</title>
			<description>${descr}</description>
			<link>${link}</link>
			<author>${author}</author>
			<guid isPermaLink="false">${id}</guid>
			<pubDate>${date}</pubDate>
		</item>
	""")
	
	image = Template( """
		<image>
			<url>${url}</url>
			<title>${title}</title>
			<link>${link}</link>
		</image>
	""")
	
	postamble = Template("""
	</channel>
</rss>""")

	def __init__(self, parent=None, *args, **kwargs ):
		super( DefaultRender,  self ).__init__( *args, **kwargs )
		self.parent = parent

	def __getattr__(self, attr ):
		"""
			Catch all attempts to access a different render-function except of list.
		"""
		try:
			return( self.__getattribute__( attr ) )
		except AttributeError: # Whatever was requested - i dont know that
			raise( errors.NotFound() )

	def list( self, skellist, **kwargs ):
		if not "rssInfo" in dir( self.parent ):
			logging.error("Cant render RSS for %s - missing rssInfo" % str( self.parent ) )
			raise( errors.NotFound() )
		rssInfo = getattr( self.parent, "rssInfo" )
		tmpDict = {	"title": "" , 
					"link": "",
					"descr": "", 
					"lang": "en", 
					"author": "", 
					"date": lambda: formatdate()
					}
		if "feed" in rssInfo.keys():
			tmpDict.update( dict( [ (k, v) for (k, v) in rssInfo["feed"].items() if k!="image" ] ) )
		if "image" in rssInfo["feed"].keys():
			imgDict = rssInfo["feed"]["image"].copy()
			for key in imgDict.keys()[ : ]:
				if callable( imgDict[ key ] ):
					imgDict[ key ] = imgDict[ key ]()
				if isinstance( imgDict[ key ], datetime ): #Its a datetime obj - format it to rfc2822
					imgDict[ key ] = formatdate( time.mktime( imgDict[ key ].timetuple() ) )
				imgDict[ key ] = HtmlSerializer().santinize( imgDict[ key ] )
			imgStr = self.image.safe_substitute( imgDict )
		else:
			imgStr = ""
		for key in tmpDict.keys()[ : ]:
			if callable( tmpDict[ key ] ):
				tmpDict[ key ] = tmpDict[ key ]()
			if isinstance( tmpDict[ key ], datetime ): #Its a datetime obj - format it to rfc2822
				tmpDict[ key ] = formatdate( time.mktime( tmpDict[ key ].timetuple() ) )
			tmpDict[ key ] = HtmlSerializer().santinize( tmpDict[ key ] )
		res = self.preamble.safe_substitute( tmpDict, image=imgStr ).lstrip()
		footer = self.postamble.safe_substitute( tmpDict ).rstrip()
		for skel in skellist:
			tmpDict = {	"title": lambda skel: skel.name.value, 
						"descr": lambda skel: skel.descr.value[ : 255], 
						"link": lambda skel: "", 
						"id": lambda skel: skel.id.value, 
						"date": lambda skel: skel.creationdate.value
					}
			tmpDict.update( dict( [ (k, v) for (k, v) in rssInfo["item"].items() if k!="image" ] ) )
			for key in tmpDict.keys()[ : ]:
				if callable( tmpDict[ key ] ):
					tmpDict[ key ] = tmpDict[ key ]( skel )
				if isinstance( tmpDict[ key ], datetime ): #Its a datetime obj - format it to rfc2822
					tmpDict[ key ] = formatdate( time.mktime( tmpDict[ key ].timetuple() ) )
				tmpDict[ key ] = HtmlSerializer().santinize( tmpDict[ key ] )
			res += self.item.safe_substitute( tmpDict )
		res += footer
		request.current.get().response.headers['Content-Type'] = "application/rss+xml"
		return( res )
