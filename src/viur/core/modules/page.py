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
    """
    A simple page construction module, allowing to create a structure of pages.
    """

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
        return [{
            "name": "pages",
            "key": self.rootnodeSkel(ensure=True)["key"],
        }]


Page.html = True
