# -*- coding: utf-8 -*-
import json
from collections import OrderedDict
from server import errors, request, bones
from server.skeleton import RefSkel, skeletonByKind
import logging

class DefaultRender(object):

	def __init__(self, parent = None, *args, **kwargs):
		super(DefaultRender,  self).__init__(*args, **kwargs)
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
			"descr": _(bone.descr),
	                "type": bone.type,
			"required": bone.required,
			"params": bone.params,
			"visible": bone.visible,
			"readonly": bone.readOnly
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
				"relskel": self.renderSkelStructure(RefSkel.fromSkel(skeletonByKind(bone.kind), *bone.refKeys))
			})


		elif bone.type == "selectone" or bone.type.startswith("selectone.") or bone.type == "selectmulti" or bone.type.startswith("selectmulti."):
			ret.update({
				"values": [(k, v) for k, v in bone.values.items()]
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
			#if "__" in key or not isinstance(bone, bones.baseBone):
			#	continue

			res[key] = self.renderBoneStructure(bone)

			if key in skel.errors:
				res[key]["error"] = skel.errors[ key ]
			elif any( [x.startswith("%s." % key) for x in skel.errors]):
				res[key]["error"] = {k:v for k,v in skel.errors.items() if k.startswith("%s." % key )}
			else:
				res[key]["error"] = None
		return [(key, val) for key, val in res.items()]

	def renderTextExtension(self, ext ):
		e = ext()
		return( {"name": e.name,
				"descr": _( e.descr ),
				"skel": self.renderSkelStructure( e.dataSkel() ) } )

	def renderBoneValue(self, bone, skel, key):
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
			if skel[key]:
				if bone.date and bone.time:
					return skel[key].strftime("%d.%m.%Y %H:%M:%S")
				elif bone.date:
					return skel[key].strftime("%d.%m.%Y")

				return skel[key].strftime("%H:%M:%S")
		elif isinstance(bone, bones.relationalBone):
			if isinstance(skel[key], list):
				refSkel = bone._refSkelCache
				usingSkel = bone._usingSkelCache
				tmpList = []
				for k in skel[key]:
					refSkel.setValuesCache(k["dest"])
					if usingSkel:
						usingSkel.setValuesCache(k.get("rel", {}))
						usingData = self.renderSkelValues(usingSkel)
					else:
						usingData = None
					tmpList.append({
						"dest": self.renderSkelValues(refSkel),
						"rel": usingData
					})

				return tmpList
			elif isinstance(skel[key], dict):
				refSkel = bone._refSkelCache
				usingSkel = bone._usingSkelCache
				refSkel.setValuesCache(skel[key]["dest"])
				if usingSkel:
					usingSkel.setValuesCache(skel[key].get("rel", {}))
					usingData = self.renderSkelValues(usingSkel)
				else:
					usingData = None
				return {
					"dest": self.renderSkelValues(refSkel),
					"rel": usingData
				}
		else:
			return skel[key]

		return None

	def renderSkelValues(self, skel):
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

		return res

	def renderEntry( self, skel, actionName ):
		if isinstance(skel, list):
			vals = [self.renderSkelValues(x) for x in skel]
			struct = self.renderSkelStructure(skel[0])
		else:
			vals = self.renderSkelValues(skel)
			struct = self.renderSkelStructure(skel)

		res = {
			"values": vals,
			"structure": struct,
			"action": actionName
		}

		request.current.get().response.headers["Content-Type"] = "application/json"
		return json.dumps(res)

	def view(self, skel, listname="view", *args, **kwargs):
		return self.renderEntry(skel, "view")

	def add(self, skel, **kwargs):
		return self.renderEntry(skel, "add")

	def edit(self, skel, **kwargs):
		return self.renderEntry(skel, "edit")

	def list(self, skellist, **kwargs):
		res = {}
		skels = []

		for skel in skellist:
			skels.append(self.renderSkelValues(skel))

		res["skellist"] = skels

		if skellist:
			res["structure"] = self.renderSkelStructure(skellist.baseSkel)
		else:
			res["structure"] = None
		res["cursor"] = skellist.cursor
		res["action"] = "list"
		request.current.get().response.headers["Content-Type"] = "application/json"
		return json.dumps(res)

	def editItemSuccess(self, skel, **kwargs):
		return self.renderEntry(skel, "editSuccess")

	def addItemSuccess(self, skel, **kwargs):
		return self.renderEntry(skel, "addSuccess")

	def deleteItemSuccess(self, skel, **kwargs):
		return self.renderEntry(skel, "deleteSuccess")

	def addDirSuccess(self, *args, **kwargs):
		return json.dumps("OKAY")

	def listRootNodes(self, rootNodes ):
		return json.dumps(rootNodes)

	def listRootNodeContents(self, subdirs, entrys, **kwargs):
		res = {
			"subdirs": subdirs
		}

		skels = []

		for skel in entrys:
			skels.append( self.renderSkelValues( skel ) )

		res["entrys"] = skels
		return json.dumps(res)

	def renameSuccess(self, *args, **kwargs):
		return json.dumps("OKAY")

	def copySuccess(self, *args, **kwargs):
		return json.dumps("OKAY")

	def deleteSuccess(self, *args, **kwargs):
		return json.dumps("OKAY")

	def reparentSuccess(self, *args, **kwargs):
		return json.dumps("OKAY")

	def setIndexSuccess(self, *args, **kwargs):
		return json.dumps("OKAY")

	def cloneSuccess(self, *args, **kwargs):
		return json.dumps("OKAY")
