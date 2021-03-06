# -*- coding: utf-8 -*-
from viur.core.prototypes.tree import Tree, TreeSkel
from viur.core.bones import *


class pageSkel(TreeSkel):
	kindName = "page"
	searchindex = "page"
	name = stringBone(descr=u"Name", indexed=True, searchable=True, required=True)
	descr = textBone(descr=u"Content", required=True, searchable=True)


class Page(Tree):
	adminInfo = {
		"name": u"Pages",  # Name of this module, as shown in ViUR Admin (will be translated at runtime)
		"handler": "tree.nodeonly.page",  # Which handler to invoke
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
			"key": repo.key
		}]


Page.html = True
Page.json = True
