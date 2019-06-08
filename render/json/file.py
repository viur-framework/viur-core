# -*- coding: utf-8 -*-
import json
from server.render.json.default import DefaultRender


class FileRender(DefaultRender):
	def renderUploadComplete(self, *args, **kwargs):
		return (json.dumps("OKAY "))

	def addDirSuccess(self, *args, **kwargs):
		return (json.dumps("OKAY"))
