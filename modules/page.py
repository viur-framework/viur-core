# -*- coding: utf-8 -*-
from server.prototypes.hierarchy import Hierarchy, HierarchySkel
from server.bones import *


class pageSkel(HierarchySkel):
	kindName = "page"
	searchindex = "page"
	name = stringBone(descr=u"Name", indexed=True, searchable=True, required=True)
	descr = textBone(descr=u"Content", required=True, searchable=True)


class Page(Hierarchy):
	adminInfo = {
		"name": u"Pages",  # Name of this module, as shown in ViUR Admin (will be translated at runtime)
		"handler": "hierarchy",  # Which handler to invoke
		"icon": "icons/modules/hierarchy.svg",  # Icon for this module
		"columns": ["name", "language", "isactive"],
		"previewurls": {
			"Web": "/{{module}}/view/{{key}}"
		}
	}

	viewTemplate = "page_view"

	def getAvailableRootNodes(self, *args, **kwargs):
		repo = self.ensureOwnModuleRootNode()
		return [{
			"name": u"pages",
			"key": str(repo.key())
		}]

	getAvailableRootNodes.internalExposed = True

	def canList(self, parent):
		return True

	def canView(self, key):
		return True


Page.html = True
Page.json = True
