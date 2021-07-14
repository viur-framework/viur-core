# -*- coding: utf-8 -*-
from viur.core.bones import relationalBone

from viur.core import request


class treeNodeBone(relationalBone):
	type = "relational.tree.node"

	def __init__(self, kind=None, format="value['dest']['name']", *args, **kwargs):
		if kind and not kind.endswith("_rootNode"):
			kind += "_rootNode"
		super(treeNodeBone, self).__init__(kind=kind, format=format, *args, **kwargs)
