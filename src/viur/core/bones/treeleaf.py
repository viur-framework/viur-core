"""
TreeLeafBone is a subclass of RelationalBone specifically designed to represent a leaf node in a tree-like data
structure. It provides an additional level of hierarchy and organization for relational data in ViUR applications.
"""
from viur.core.bones.relational import RelationalBone


class TreeLeafBone(RelationalBone):
    """
    TreeLeafBone is a subclass of RelationalBone specifically designed to represent a leaf node in a tree-like data
    structure. It provides an additional level of hierarchy and organization for relational data in ViUR applications.
    """
    type = "relational.tree.leaf"

    def __init__(self, **kwargs):
        super(TreeLeafBone, self).__init__(**kwargs)
