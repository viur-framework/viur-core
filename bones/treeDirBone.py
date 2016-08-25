# -*- coding: utf-8 -*-
from server.bones import relationalBone

from server import request

class treeDirBone( relationalBone ):

	def __init__(self, kind=None, format="$(dest.name)", *args, **kwargs):
		if kind and not kind.endswith("_rootNode"):
			kind += "_rootNode"
		super( treeDirBone, self ).__init__(kind=kind, format=format, *args, **kwargs)

