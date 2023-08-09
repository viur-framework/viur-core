"""
TreeNodeBone is a subclass of RelationalBone specifically designed to represent an intermediate node in a tree-like
data structure. It provides a way to define hierarchical relationships between entities in a ViUR application.

The TreeNodeBone is of type "relational.tree.node", which distinguishes it from other RelationalBone subclasses.
"""
from viur.core.bones.relational import RelationalBone


class TreeNodeBone(RelationalBone):
    """
    TreeNodeBone is a subclass of RelationalBone specifically designed to represent an intermediate node in a tree-like
    data structure. It provides a way to define hierarchical relationships between entities in a ViUR application.

    The TreeNodeBone is of type "relational.tree.node", which distinguishes it from other RelationalBone subclasses.
    """
    type = "relational.tree.node"
