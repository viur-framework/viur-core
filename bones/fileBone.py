# -*- coding: utf-8 -*-
from viur.core.bones import treeLeafBone
from viur.core import db, request, conf
from viur.core.utils import downloadUrlFor
from viur.core.tasks import callDeferred
# from google.appengine.api import images
from hashlib import sha256
import logging
from typing import Union, Dict
from itertools import chain


@callDeferred
def ensureDerived(key: str, name: str, deriveMap: Dict[str, Dict]):
	"""
	Ensure that pending thumbnails or other derived Files are build
	:param dlkey:
	:param name:
	:param deriveMap:
	:return:
	"""
	from viur.core.skeleton import skeletonByKind
	skel = skeletonByKind("file")()
	if not skel.fromDB(key):
		logging.warning("ensureDerived failed: Entry %s disappeared!" % key)
	if not skel["derived"]:
		logging.info("No Derives for this file")
		skel["derived"] = {}
	didBuild = False
	for fileName, params in deriveMap.items():
		if fileName not in skel["derived"]:
			deriveFuncMap = conf["viur.file.derivers"]
			if not "callee" in params:
				assert False
			if not params["callee"] in deriveFuncMap:
				raise NotImplementedError("Callee not registered")
			callee = deriveFuncMap[params["callee"]]
			callRes = callee(skel, fileName, params)
			if callRes:
				fileName, size, mimetype = callRes
				skel["derived"][fileName] = {"name": fileName, "size": size, "mimetype": mimetype, "params": params}
			didBuild = True
	if didBuild:
		skel.toDB()


class fileBone(treeLeafBone):
	kind = "file"
	type = "relational.tree.leaf.file"
	refKeys = ["name", "key", "mimetype", "dlkey", "size", "width", "height", "derived"]

	def __init__(self, format="$(dest.name)", derive: Union[None, Dict[str, Dict]] = None, *args, **kwargs):
		if "dlkey" not in self.refKeys:
			self.refKeys.append("dlkey")
		super(fileBone, self).__init__(format=format, *args, **kwargs)
		self.derive = derive

	def postSavedHandler(self, skel, boneName, key):
		super().postSavedHandler(skel, boneName, key)
		values = skel[boneName]
		if self.derive and values:
			if isinstance(values, dict):
				values = [values]
			for val in values:
				ensureDerived(val["dest"]["key"], val["dest"]["name"], self.derive)

	def getReferencedBlobs(self, skel, name):
		val = skel[name]
		if val is None:
			return []
		if self.languages and self.multiple:
			return chain(*[[y["dest"]["dlkey"] for y in x] for x in val.values() if x])
		elif self.languages:
			return [x["dest"]["dlkey"] for x in val.values() if x]
		elif self.multiple:
			return [x["dest"]["dlkey"] for x in val]
		else:
			return [val["dest"]["dlkey"]]

	def refresh(self, skel, boneName):
		from viur.core.modules.file import importBlobFromViur2
		super().refresh(skel, boneName)
		if conf.get("viur.viur2import.blobsource"):
			# Just ensure the file get's imported as it may not have an file entry
			val = skel[boneName]
			if isinstance(val, list):
				for x in val:
					importBlobFromViur2(x["dest"]["dlkey"])
			elif isinstance(val, dict):
				importBlobFromViur2(val["dest"]["dlkey"])
