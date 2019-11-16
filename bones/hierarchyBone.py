# -*- coding: utf-8 -*-
from viur.server.bones import relationalBone


class hierarchyBone(relationalBone):
	def __init__(self, *args, **kwargs):
		super(hierarchyBone, self).__init__(*args, **kwargs)
