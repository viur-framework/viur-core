# -*- coding: utf-8 -*-
import re
class regex(object):

	def getfilters(self):
		return {
		}

	def getglobals(self):
		return {
			"regex_replace":self.regex_replace,
			"regex_search":self.regex_search,
			"regex_match":self.regex_match
		}

	def getExtension(self):
		return [] # list of Extension classes__author__ = 'ak'

	def regex_replace(self,s, find, replace):
		return re.sub(find, replace, s)

	def regex_search(self,pattern,string, flags=0):
		return re.search(pattern, string, flags)

	def regex_match(self,pattern,string):
		return re.match(pattern,string)
