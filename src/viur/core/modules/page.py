from viur.core.prototypes.tree import Tree, TreeSkel
from viur.core.bones import *


class PageSkel(TreeSkel):
    kindName = "page"
    searchindex = "page"

    name = StringBone(
        descr="Name",
        searchable=True,
        required=True
    )

    descr = TextBone(
        descr="Content",
        required=True,
        searchable=True
    )


class Page(Tree):
    adminInfo = {
        "name": "Pages",
        "handler": "tree.nodeonly.page",
        "icon": "cloud-fill",
        "columns": ["name", "language", "isactive"],
        "preview": {
            "Web": "/{{module}}/view/{{key}}"
        }
    }

    viewTemplate = "page_view"

    def getAvailableRootNodes(self, *args, **kwargs):
        repo = self.ensureOwnModuleRootNode()
        return [{
            "name": "pages",
            "key": repo.key
        }]


Page.html = True
Page.json = True
