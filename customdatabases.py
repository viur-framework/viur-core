# -*- coding: utf-8 -*-

from server.skeleton import Skeleton, CustomDatabaseAdapter
from server.bones import *
from server import db
from typing import Set, List
from server.config import conf

class ViurTagsSearchAdapter(CustomDatabaseAdapter):
	providesFulltextSeach = True

	def __init__(self, indexFields: Set[str], minLength: int = 3, enforceQueryConstraints: bool = False):
		super(ViurTagsSearchAdapter, self).__init__()
		self.indexFields = indexFields
		self.minLength = minLength
		self.fulltextSearchGuaranteesQueryConstrains = enforceQueryConstraints

	def _tagsFromString(self, value):
		resSet = set()
		for tag in value.split(" "):
			tag = "".join([x for x in tag.lower() if x in conf["viur.searchValidChars"]])
			if len(tag) > self.minLength:
				resSet.add(tag)
		return resSet

	def preprocessEntry(self, entry: db.Entity, skel: Skeleton, changeList: List[str], isAdd: bool):
		def tagsFromSkel(skel):
			tags = set()
			for boneName, bone in skel.items():
				value = skel[boneName]
				if boneName in self.indexFields:
					if isinstance(bone, (stringBone, textBone)):
						if isinstance(value, str):
							tags = tags.union(self._tagsFromString(value))
						elif isinstance(value, list):
							for val in value:
								tags = tags.union(self._tagsFromString(val))
						elif isinstance(value, dict):
							for val in value.values():
								if isinstance(val, list):
									for v in val:
										tags = tags.union(self._tagsFromString(v))
								else:
									tags = tags.union(self._tagsFromString(val))
			return tags

		tags = tagsFromSkel(skel)
		entry["viurTags"] = list(tags)
		return entry

	def fulltextSearch(self, queryString, databaseQuery):
		keywords = list(self._tagsFromString(queryString))[:5]
		resultScoreMap = {}
		resultEntryMap = {}
		for keyword in keywords:
			if self.fulltextSearchGuaranteesQueryConstrains:
				qryBase = databaseQuery.clone()
			else:
				qryBase = db.Query(databaseQuery.getKind())
			for entry in qryBase.filter("viurTags AC", keyword).run():
				if not entry.name in resultScoreMap:
					resultScoreMap[entry.name] = 1
				else:
					resultScoreMap[entry.name] += 1
				if not entry.name in resultEntryMap:
					resultEntryMap[entry.name] = entry
		resultList = [(k, v) for k, v in resultScoreMap.items()]
		resultList.sort(key=lambda x: x[1])
		resList = [resultEntryMap[x[0]] for x in resultList[:databaseQuery.amount]]
		return resList
