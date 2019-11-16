# -*- coding: utf-8 -*-
from viur.server.bones.bone import baseBone


class keyBone(baseBone):
	kind = "key"

	def __init__(self, descr="Key", readOnly=True, visible=False, **kwargs):
		super(keyBone, self).__init__(descr=descr, readOnly=readOnly, visible=visible, **kwargs)


