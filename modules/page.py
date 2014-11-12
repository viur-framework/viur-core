# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server.applications.hierarchy import Hierarchy, HierarchySkel
from server.bones import *
from server import db
from server import session, errors
from server.plugins.text.youtube import YouTube
import logging

class pageSkel( HierarchySkel ):
	kindName="page"
	searchindex = "page"
	name = stringBone( descr="Name", indexed=True, searchable=True, required=True )
	descr = textBone( descr="Content", required=True, searchable=True, extensions=[YouTube] )

class Page( Hierarchy ):
	adminInfo = {	"name": "Sites", #Name of this modul, as shown in ViUR Admin (will be translated at runtime)
				"handler": "hierarchy",  #Which handler to invoke
				"icon": "icons/modules/hierarchy.svg", #Icon for this modul
				"formatstring": "$(name)", 
				"filters" : { 	
							None: { "filter":{ },
									"icon":"icons/modules/hierarchy.svg",
									"columns":["name", "language", "isactive"]
							},
					},
				"previewURL": "/page/view/{{id}}"
				}

	viewTemplate = "page_view"

	def getAvailableRootNodes( self, *args, **kwargs ):
		repo = self.ensureOwnModulRootNode()
		return( [{"name":u"Seiten", "key": str( repo.key() ) }] )
	getAvailableRootNodes.internalExposed=True

	def canList( self, parent ):
		return( True )
		
	def canView( self, id ):
		return( True )
	
Page.jinja2 = True
Page.json = True
