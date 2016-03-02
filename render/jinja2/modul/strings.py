# -*- coding: utf-8 -*-
import json
class strings(object):

	def getfilters(self):
		return {
			"clearString":self.clearString
		}

	def getglobals(self):
		return {
			"getJson":self.getJson
		}

	def getExtension(self):
		return [] # list of Extension classes

	def clearString(self, str, words):
		for w in words:
			str = str.replace(w, "")
		return str

	def getJson(self, str):
		return json.loads(str) or None
