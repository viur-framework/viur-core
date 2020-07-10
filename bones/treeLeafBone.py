# -*- coding: utf-8 -*-
from viur.core.bones import relationalBone


class treeLeafBone(relationalBone):
	type = "relational.tree.leaf"

	def __init__(self, *args, **kwargs):
		super(treeLeafBone, self).__init__(*args, **kwargs)
