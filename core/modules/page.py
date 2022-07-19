from viur.core.prototypes.tree import Tree, TreeSkel
from viur.core.bones import *


class pageSkel(TreeSkel):
    kindName = "page"
    searchindex = "page"
    name = StringBone(descr=u"Name", indexed=True, searchable=True, required=True)
    descr = TextBone(descr=u"Content", required=True, searchable=True)


class Page(Tree):
    adminInfo = {
        "name": u"Pages",  # Name of this module, as shown in ViUR Admin (will be translated at runtime)
        "handler": "tree.nodeonly.page",  # Which handler to invoke
        "icon": "icon-cloud",  # Icon for this module
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
