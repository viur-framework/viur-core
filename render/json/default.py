# -*- coding: utf-8 -*-
import json
from collections import OrderedDict
from viur.core import errors, bones, utils
from viur.core.skeleton import RefSkel, skeletonByKind, BaseSkeleton, SkeletonInstance
from viur.core.utils import currentRequest

class DefaultRender(object):

	def __init__(self, parent=None, *args, **kwargs):
		super(DefaultRender, self).__init__(*args, **kwargs)
		self.parent = parent

	def renderBoneStructure(self, bone):
		"""
		Renders the structure of a bone.

		This function is used by `renderSkelStructure`.
		can be overridden and super-called from a custom renderer.

		:param bone: The bone which structure should be rendered.
		:type bone: Any bone that inherits from :class:`server.bones.base.baseBone`.

		:return: A dict containing the rendered attributes.
		:rtype: dict
		"""

		# Base bone contents.
		ret = {
			"descr": str(bone.descr),
			"type": bone.type,
			"required": bone.required,
			"params": bone.params,
			"visible": bone.visible,
			"readonly": bone.readOnly,
			"unique": bone.unique.method.value if bone.unique else False,
			"languages": bone.languages,
			"multiple": bone.multiple
		}

		if bone.type == "relational" or bone.type.startswith("relational."):
			if isinstance(bone, bones.hierarchyBone):
				boneType = "hierarchy"
			elif isinstance(bone, bones.treeItemBone):
				boneType = "treeitem"
			elif isinstance(bone, bones.treeDirBone):
				boneType = "treedir"
			else:
				boneType = "relational"
			ret.update({
				"type": "%s.%s" % (boneType, bone.kind),
				"module": bone.module,
				"multiple": bone.multiple,
				"format": bone.format,
				"using": self.renderSkelStructure(bone.using()) if bone.using else None,
				"relskel": self.renderSkelStructure(bone._refSkelCache())
			})

		elif bone.type == "record" or bone.type.startswith("record."):
			ret.update({
				"multiple": bone.multiple,
				"format": bone.format,
				"using": self.renderSkelStructure(bone.using())
			})

		elif bone.type == "select" or bone.type.startswith("select."):
			ret.update({
				"values": [(k, str(v)) for k, v in bone.values.items()],
				"multiple": bone.multiple,
			})

		elif bone.type == "date" or bone.type.startswith("date."):
			ret.update({
				"date": bone.date,
				"time": bone.time
			})

		elif bone.type == "numeric" or bone.type.startswith("numeric."):
			ret.update({
				"precision": bone.precision,
				"min": bone.min,
				"max": bone.max
			})

		elif bone.type == "text" or bone.type.startswith("text."):
			ret.update({
				"validHtml": bone.validHtml,
				"languages": bone.languages
			})

		elif bone.type == "str" or bone.type.startswith("str."):
			ret.update({
				"multiple": bone.multiple,
				"languages": bone.languages
			})

		return ret

	def renderSkelStructure(self, skel):
		"""
		Dumps the structure of a :class:`server.db.skeleton.Skeleton`.

		:param skel: Skeleton which structure will be processed.
		:type skel: server.db.skeleton.Skeleton

		:returns: The rendered dictionary.
		:rtype: dict
		"""
		if isinstance(skel, dict):
			return None
		res = OrderedDict()
		for key, bone in skel.items():
			# if "__" in key or not isinstance(bone, bones.baseBone):
			#	continue

			res[key] = self.renderBoneStructure(bone)

			# FIXME!
			#if key in skel.errors:
			#	res[key]["error"] = skel.errors[key]
			#elif any([x.startswith("%s." % key) for x in skel.errors.keys()]):
			#	res[key]["error"] = {k: v for k, v in skel.errors.items() if k.startswith("%s." % key)}
			#else:
			#	res[key]["error"] = None
			res[key]["error"] = None
		return [(key, val) for key, val in res.items()]

	def renderTextExtension(self, ext):
		e = ext()
		return ({"name": e.name,
				 "descr": str(e.descr),
				 "skel": self.renderSkelStructure(e.dataSkel())})

	def renderSingleBoneValue(self, value, bone, skel, key):
		"""
		Renders the value of a bone.

		This function is used by :func:`collectSkelData`.
		It can be overridden and super-called from a custom renderer.

		:param bone: The bone which value should be rendered.
		:type bone: Any bone that inherits from :class:`server.bones.base.baseBone`.

		:return: A dict containing the rendered attributes.
		:rtype: dict
		"""
		if bone.type == "date" or bone.type.startswith("date."):
			if value:
				if bone.date and bone.time:
					return value.strftime("%d.%m.%Y %H:%M:%S")
				elif bone.date:
					return value.strftime("%d.%m.%Y")

				return value.strftime("%H:%M:%S")
		elif isinstance(bone, bones.relationalBone):
			if isinstance(value, dict):
				return {
					"dest": self.renderSkelValues(value["dest"], injectDownloadURL=isinstance(bone, bones.fileBone)),
					"rel": self.renderSkelValues(value["rel"], injectDownloadURL=isinstance(bone, bones.fileBone)) if value["rel"] else None,
				}
		elif isinstance(bone, bones.recordBone):
			tmpList = []
			if value:
				for k in value:
					tmpList.append(self.renderSkelValues(k))
			return tmpList
		elif isinstance(bone, bones.keyBone):
			v = skel["key"]
			return v.to_legacy_urlsafe().decode("ASCII") if v else None
		else:
			return value
		return None
	
	def renderBoneValue(self, bone, skel, key):
		boneVal = skel[key]
		if bone.languages and bone.multiple:
			res = {}
			for language in bone.languages:
				if boneVal and language in boneVal and boneVal[language]:
					res[language] = [self.renderSingleBoneValue(v, bone, skel, key) for v in boneVal[language]]
				else:
					res[language] = []
		elif bone.languages:
			res = {}
			for language in bone.languages:
				if boneVal and language in boneVal and boneVal[language]:
					res[language] = self.renderSingleBoneValue(boneVal[language], bone, skel, key)
				else:
					res[language] = None
		elif bone.multiple:
			res = [self.renderSingleBoneValue(v, bone, skel, key) for v in boneVal] if boneVal else None
		else:
			res = self.renderSingleBoneValue(boneVal, bone, skel, key)
		return res

	def renderSkelValues(self, skel, injectDownloadURL=False):
		"""
		Prepares values of one :class:`server.db.skeleton.Skeleton` or a list of skeletons for output.

		:param skel: Skeleton which contents will be processed.
		:type skel: server.db.skeleton.Skeleton

		:returns: A dictionary or list of dictionaries.
		:rtype: dict
		"""
		if skel is None:
			return None
		elif isinstance(skel, dict):
			return skel
		res = {}
		for key, bone in skel.items():
			res[key] = self.renderBoneValue(bone, skel, key)
		if injectDownloadURL and "dlkey" in skel and "name" in skel:
			res["downloadUrl"] = utils.downloadUrlFor(skel["dlkey"], skel["name"], derived=False)
		return res

	def renderEntry(self, skel, actionName, params=None):
		if isinstance(skel, list):
			vals = [self.renderSkelValues(x) for x in skel]
			struct = self.renderSkelStructure(skel[0])
			errors = None
		elif isinstance(skel, SkeletonInstance):
			vals = self.renderSkelValues(skel)
			struct = self.renderSkelStructure(skel)
			errors = [{"severity": x.severity.value, "fieldPath": x.fieldPath, "errorMessage": x.errorMessage} for x in skel.errors]
		else:  # Hopefully we can pass it directly...
			vals = skel
			struct = None
			errors = None
		res = {
			"values": vals,
			"structure": struct,
			"errors": errors,
			"action": actionName,
			"params": params
		}
		currentRequest.get().response.headers["Content-Type"] = "application/json"
		return json.dumps(res)

	def view(self, skel, action="view", params=None, *args, **kwargs):
		return self.renderEntry(skel, action, params)

	def add(self, skel, action="add", params=None, **kwargs):
		return self.renderEntry(skel, action, params)

	def edit(self, skel, action="edit", params=None, **kwargs):
		return self.renderEntry(skel, action, params)

	def list(self, skellist, action="list", params=None, **kwargs):
		res = {}
		skels = []
		for skel in skellist:
			skels.append(self.renderSkelValues(skel))
		res["skellist"] = skels
		if skellist:
			res["structure"] = self.renderSkelStructure(skellist.baseSkel)
		else:
			res["structure"] = None
		try:
			res["cursor"] = "h-%s" % skellist.getCursor().hex()
		except:
			res["cursor"] = None
		res["action"] = action
		res["params"] = params
		currentRequest.get().response.headers["Content-Type"] = "application/json"
		return json.dumps(res)

	def editItemSuccess(self, skel, params=None, **kwargs):
		return self.renderEntry(skel, "editSuccess", params)

	def addItemSuccess(self, skel, params=None, **kwargs):
		return self.renderEntry(skel, "addSuccess", params)

	def addDirSuccess(self, rootNode, path, dirname, params=None, *args, **kwargs):
		return json.dumps("OKAY")

	def listRootNodes(self, rootNodes, tpl=None, params=None):
		for rn in rootNodes:
			rn["key"] = rn["key"].to_legacy_urlsafe().decode("ASCII")
		return json.dumps(rootNodes)

	def listRootNodeContents(self, subdirs, entrys, tpl=None, params=None, **kwargs):
		res = {
			"subdirs": subdirs
		}

		skels = []

		for skel in entrys:
			skels.append(self.renderSkelValues(skel))

		res["entrys"] = skels
		return json.dumps(res)

	def renameSuccess(self, rootNode, path, src, dest, params=None, *args, **kwargs):
		return json.dumps("OKAY")

	def copySuccess(self, srcrepo, srcpath, name, destrepo, destpath, type, deleteold, params=None, *args, **kwargs):
		return json.dumps("OKAY")

	def deleteSuccess(self, skel, params=None, *args, **kwargs):
		return json.dumps("OKAY")

	def reparentSuccess(self, obj, tpl=None, params=None, *args, **kwargs):
		return json.dumps("OKAY")

	def setIndexSuccess(self, obj, tpl=None, params=None, *args, **kwargs):
		return json.dumps("OKAY")

	def cloneSuccess(self, tpl=None, params=None, *args, **kwargs):
		return json.dumps("OKAY")
