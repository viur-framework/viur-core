from viur.core.bones.relational import RelationalBone


class TreeNodeBone(RelationalBone):
	type = "relational.tree.node"

	def __init__(self, *, kind=None, format="value['dest']['name']", **kwargs):
		if kind and not kind.endswith("_rootNode"):
			kind += "_rootNode"
		super(TreeNodeBone, self).__init__(kind=kind, format=format, *args, **kwargs)
