# -*- coding: utf-8 -*-

from viur.core.skeleton import Skeleton, CustomDatabaseAdapter
from viur.core.bones import *
from viur.core import db
from typing import Set, List
from viur.core.config import conf

class ViurTagsSearchAdapter(CustomDatabaseAdapter):
	providesFulltextSearch = True

	def __init__(self, indexFields: Set[str], minLength: int = 3, enforceQueryConstraints: bool = False):
		super(ViurTagsSearchAdapter, self).__init__()
		self.indexFields = indexFields
		self.minLength = minLength
		self.fulltextSearchGuaranteesQueryConstrains = enforceQueryConstraints

	def _tagsFromString(self, value):
		resSet = set()
		for tag in value.split(" "):
			tag = "".join([x for x in tag.lower() if x in conf["viur.searchValidChars"]])
			if len(tag) >= self.minLength:
				resSet.add(tag)
			for x in range(1, 1+len(tag)-self.minLength):
				resSet.add(tag[x:])
		return resSet

	def preprocessEntry(self, entry: db.Entity, skel: Skeleton, changeList: List[str], isAdd: bool):
		def tagsFromSkel(skel):
			tags = set()
			for boneName, bone in skel.items():
				if bone.searchable:
					tags = tags.union(bone.getSearchTags(skel, boneName))
			return tags

		tags = tagsFromSkel(skel)
		entry["viurTags"] = list(tags)
		return entry

	def fulltextSearch(self, queryString, databaseQuery):
		keywords = list(self._tagsFromString(queryString))[:10]
		resultScoreMap = {}
		resultEntryMap = {}
		for keyword in keywords:
			if self.fulltextSearchGuaranteesQueryConstrains:
				qryBase = databaseQuery.clone()
			else:
				qryBase = db.Query(databaseQuery.getKind())
			for entry in qryBase.filter("viurTags >=", keyword).filter("viurTags <", keyword+"\ufffd").run():
				if not entry.key in resultScoreMap:
					resultScoreMap[entry.key] = 1
				else:
					resultScoreMap[entry.key] += 1
				if not entry.key in resultEntryMap:
					resultEntryMap[entry.key] = entry
		resultList = [(k, v) for k, v in resultScoreMap.items()]
		resultList.sort(key=lambda x: x[1])
		resList = [resultEntryMap[x[0]] for x in resultList[:databaseQuery.amount]]
		return resList
