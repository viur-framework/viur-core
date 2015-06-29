# -*- coding: utf-8 -*-
from server.bones import relationalBone

from server import request

class treeDirBone( relationalBone ):

	def __init__(self, type=None, format="$(name)",*args, **kwargs ):
		if type and not type.endswith("_rootNode"):
			type += "_rootNode"
		super( treeDirBone, self ).__init__( type=type, format=format, *args, **kwargs )

