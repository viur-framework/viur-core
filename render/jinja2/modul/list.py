# -*- coding: utf-8 -*-
import random
class list(object):

	def getfilters(self):
		return {
			"shuffleList":self.shuffleList,
			"listattr":self.listattr,
			"isList":self.isList
		}

	def getglobals(self):
		return {
			"sortList":self.sortList,
			"randomList":self.randomList
		}

	def getExtension(self):
		return [] # list of Extension classes

	def randomList(self, start=0, end=0, amount=0):
		return random.sample(range(start, end), amount)

	#felder können auch mit . getrennt werdenz.b name.rel.nummer
	def sortList(self,List,field,reverse=False):
		fields = field.split(".")
		sortedids={}
		for i in List:
			entry=i
			for afield in fields: #z.b. [name,rel,nummer]
				entry = entry[afield]
				if isinstance(entry,list) and len(entry)>0 and isinstance(entry[0],basestring): #wenn entry[0] ein string und entry ist liste
					entry=sorted(entry)[0]
			sortedids.update({i["id"]:entry})#sortierte liste mit id speichern

		sortedids= sorted(sortedids.iteritems(), key=lambda (k,v): (v,k),reverse=reverse) # sortieren

		sortedList=[]
		for id,name in sortedids:
			for i in List:
				if id ==i["id"]:
					sortedList.append(i) #neu zusammen bauen
		return sortedList

	def shuffleList(self,skellist,amount=0):
		random.shuffle(skellist)
		if amount>0:
			skellist=skellist[:amount]
		return skellist

	#gibt eine Liste von Feldern in einer Liste zurück z.b. eine idliste
	def listattr(self,list,attrname):
		attrlist = []
		for i in list:
			if attrname in i.keys():
				attrlist.append(str(i[attrname]))
			elif "dest" in i and attrname in i["dest"].keys():
				attrlist.append(str(i["dest"][attrname]))
		return (attrlist)

	#ab 2.6 nicht mehr nötig => mapper
	def isList(self,obj):
		if isinstance(obj,list)==True:
			return True
		return False