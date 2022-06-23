from viur.core.bones.relational import RelationalBone


class TreeLeafBone(RelationalBone):
    type = "relational.tree.leaf"

    def __init__(self, **kwargs):
        super(TreeLeafBone, self).__init__(**kwargs)
