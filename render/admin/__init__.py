# -*- coding: utf-8 -*-

from viur.core.render.json.default import DefaultRender
from viur.core.render.json.user import UserRender as user
from viur.core.render.json.file import FileRender as file
from viur.core.utils import currentRequest, currentLanguage
from viur.core.skeleton import SkeletonInstance
from viur.core import conf
from viur.core import securitykey
from viur.core import utils
import datetime, json

class default(DefaultRender):
		kind = "json.admin"

__all__ = [default]


def genSkey(*args, **kwargs):
	return json.dumps(securitykey.create())


genSkey.exposed = True


def timestamp(*args, **kwargs):
	d = datetime.datetime.now()
	return (json.dumps(d.strftime("%Y-%m-%dT%H-%M-%S")))


timestamp.exposed = True


def getStructure(adminTree, module):
	from viur.core.prototypes.uniformtree import TreeType
	if not module in dir(adminTree) \
		or not "adminInfo" in dir(getattr(adminTree, module)) \
		or not getattr(adminTree, module).adminInfo:
		# Module not known or no adminInfo for that module
		return (json.dumps(None))
	res = {}
	try:
		moduleObj = getattr(adminTree, module)
	except:
		return (None)
	for stype in ["viewSkel", "editSkel", "addSkel", "viewLeafSkel", "viewNodeSkel", "editNodeSkel", "editLeafSkel",
				  "addNodeSkel", "addLeafSkel"]:  # Unknown skel type
		if stype in dir(moduleObj):
			try:
				skel = getattr(moduleObj, stype)()
			except TypeError:
				continue
			if isinstance(skel, SkeletonInstance):
				res[stype] = default().renderSkelStructure(skel)
	if not res and "nodeSkelCls" in dir(moduleObj):
		# Try Node/Leaf
		for stype in ["viewSkel", "editSkel", "addSkel"]:
			for treeType in [TreeType.Node, TreeType.Leaf]:
				if stype in dir(moduleObj):
					try:
						skel = getattr(moduleObj, stype)(treeType)
					except TypeError:
						continue
					if isinstance(skel, SkeletonInstance):
						storeType = stype.replace("Skel", "")+("LeafSkel" if treeType == TreeType.Leaf else "NodeSkel")
						res[storeType] = default().renderSkelStructure(skel)
	if res:
		return (json.dumps(res))
	else:
		return (json.dumps(None))


def setLanguage(lang, skey):
	if not securitykey.validate(skey):
		return
	if lang in conf["viur.availableLanguages"]:
		currentLanguage.set(lang)


setLanguage.exposed = True


def dumpConfig(adminTree):
	adminConfig = {}
	for key in dir(adminTree):
		app = getattr(adminTree, key)
		if "adminInfo" in dir(app) and app.adminInfo:
			if callable(app.adminInfo):
				info = app.adminInfo()
				if info is not None:
					adminConfig[key] = info
			else:
				adminConfig[key] = app.adminInfo.copy()
				adminConfig[key]["name"] = str(adminConfig[key]["name"])
				adminConfig[key]["views"] = []
				if "views" in app.adminInfo:
					for v in app.adminInfo["views"]:
						tmp = v.copy()
						tmp["name"] = str(tmp["name"])
						adminConfig[key]["views"].append(tmp)
	res = {"capabilities": conf["viur.capabilities"],
		   "modules": adminConfig,
		   "configuration": {}
		   }
	for k, v in conf.items():
		if k.lower().startswith("admin."):
			res["configuration"][k[6:]] = v

	if "viur.defaultlangs" in conf:
		res["viur.defaultlangs"] = conf["viur.defaultlangs"]
	if "viur.defaultlangsvalues" in conf:
		res["viur.defaultlangsvalues"] = conf["viur.defaultlangsvalues"]
	return json.dumps(res)


def getVersion(*args, **kwargs):
	# We force the patch-level of our version to be always zero for security reasons
	return json.dumps((conf["viur.version"][0], conf["viur.version"][1], 0))


getVersion.exposed = True


def canAccess(*args, **kwargs):
	user = utils.getCurrentUser()
	if user and ("root" in user["access"] or "admin" in user["access"]):
		return True

	pathList = currentRequest.get().pathlist

	if len(pathList) >= 2 and pathList[1] in ["skey", "getVersion"]:
		# Give the user the chance to login :)
		return True

	if (len(pathList) >= 3
		and pathList[1] == "user"
		and (pathList[2].startswith("auth_")
			 or pathList[2].startswith("f2_")
			 or pathList[2] == "getAuthMethods"
			 or pathList[2] == "logout")):
		# Give the user the chance to login :)
		return True

	if (len(pathList) >= 4
		and pathList[1] == "user"
		and pathList[2] == "view"
		and pathList[3] == "self"):
		# Give the user the chance to view himself.
		return True

	return False


def _postProcessAppObj(obj):
	obj["skey"] = genSkey
	obj["timestamp"] = timestamp
	obj["config"] = lambda *args, **kwargs: dumpConfig(conf["viur.mainApp"].admin)
	obj["config"].exposed = True
	obj["getStructure"] = lambda *args, **kwargs: getStructure(conf["viur.mainApp"].admin, *args, **kwargs)
	obj["getStructure"].exposed = True
	obj["canAccess"] = canAccess
	obj["setLanguage"] = setLanguage
	obj["getVersion"] = getVersion
	return obj
