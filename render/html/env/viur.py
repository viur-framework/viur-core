# -*- coding: utf-8 -*-
from viur.core import utils, request, conf, prototypes, securitykey, errors, db
from viur.core.skeleton import SkeletonInstance, RelSkel
from viur.core.render.html.utils import jinjaGlobalFunction, jinjaGlobalFilter
import urllib, urllib.parse
from hashlib import sha512
#from google.appengine.ext import db
#from google.appengine.api import memcache, users
from datetime import timedelta
from collections import OrderedDict
import string
import logging
import os
from typing import List
from viur.core.utils import currentSession, currentRequest, currentLanguage


@jinjaGlobalFunction
def execRequest(render, path, *args, **kwargs):
	"""
	Jinja2 global: Perform an internal Request.

	This function allows to embed the result of another request inside the current template.
	All optional parameters are passed to the requested resource.

	:param path: Local part of the url, e.g. user/list. Must not start with an /.
	Must not include an protocol or hostname.
	:type path: str

	:returns: Whatever the requested resource returns. This is *not* limited to strings!
	"""
	if "cachetime" in kwargs:
		cachetime = kwargs["cachetime"]
		del kwargs["cachetime"]
	else:
		cachetime = 0
	if conf["viur.disableCache"] or currentRequest.get().disableCache:  # Caching disabled by config
		cachetime = 0
	cacheEnvKey = None
	if conf["viur.cacheEnvironmentKey"]:
		try:
			cacheEnvKey = conf["viur.cacheEnvironmentKey"]()
		except RuntimeError:
			cachetime = 0
	if cachetime:
		# Calculate the cache key that entry would be stored under
		tmpList = ["%s:%s" % (str(k), str(v)) for k, v in kwargs.items()]
		tmpList.sort()
		tmpList.extend(list(args))
		tmpList.append(path)
		if cacheEnvKey is not None:
			tmpList.append(cacheEnvKey)
		try:
			appVersion = currentRequest.get().request.environ["CURRENT_VERSION_ID"].split('.')[0]
		except:
			appVersion = ""
			logging.error("Could not determine the current application id! Caching might produce unexpected results!")
		tmpList.append(appVersion)
		mysha512 = sha512()
		mysha512.update(str(tmpList).encode("UTF8"))
		cacheKey = "jinja2_cache_%s" % mysha512.hexdigest()
		res = None  # memcache.get(cacheKey)
		if res:
			return res
	currReq = currentRequest.get()
	tmp_params = currReq.kwargs.copy()
	currReq.kwargs = {"__args": args, "__outer": tmp_params}
	currReq.kwargs.update(kwargs)
	lastRequestState = currReq.internalRequest
	currReq.internalRequest = True
	caller = conf["viur.mainApp"]
	pathlist = path.split("/")
	for currpath in pathlist:
		if currpath in dir(caller):
			caller = getattr(caller, currpath)
		elif "index" in dir(caller) and hasattr(getattr(caller, "index"), '__call__'):
			caller = getattr(caller, "index")
		else:
			currReq.kwargs = tmp_params  # Reset RequestParams
			currReq.internalRequest = lastRequestState
			return (u"Path not found %s (failed Part was %s)" % (path, currpath))
	if (not hasattr(caller, '__call__')
			or ((not "exposed" in dir(caller)
				 or not caller.exposed))
			and (not "internalExposed" in dir(caller)
				 or not caller.internalExposed)):
		currReq.kwargs = tmp_params  # Reset RequestParams
		currReq.internalRequest = lastRequestState
		return (u"%s not callable or not exposed" % str(caller))
	try:
		resstr = caller(*args, **kwargs)
	except Exception as e:
		logging.error("Caught execption in execRequest while calling %s" % path)
		logging.exception(e)
		raise
	currReq.kwargs = tmp_params
	currReq.internalRequest = lastRequestState
	if cachetime:
		pass
		#memcache.set(cacheKey, resstr, cachetime)
	return resstr


@jinjaGlobalFunction
def getCurrentUser(render):
	"""
	Jinja2 global: Returns the current user from the session, or None if not logged in.

	:return: A dict containing user data. Returns None if no user data is available.
	:rtype: dict
	"""
	return utils.getCurrentUser()


@jinjaGlobalFunction
def getSkel(render, module, key=None, skel="viewSkel"):
	"""
	Jinja2 global: Fetch an entry from a given module, and return the data as a dict,
	prepared for direct use in the output.

	It is possible to specify a different data-model as the one used for rendering
	(e.g. an editSkel).

	:param module: Name of the module, from which the data should be fetched.
	:type module: str

	:param key: Requested entity-key in an urlsafe-format. If the module is a Singleton
	application, the parameter can be omitted.
	:type key: str

	:param skel: Specifies and optionally different data-model
	:type skel: str

	:returns: dict on success, False on error.
	:rtype: dict | bool
	"""
	if module not in dir(conf["viur.mainApp"]):
		logging.error("getEntry called with unknown module %s!" % module)
		return False

	obj = getattr(conf["viur.mainApp"], module)

	if skel in dir(obj):
		skel = getattr(obj, skel)()

		if isinstance(obj, prototypes.singleton.Singleton) and not key:
			# We fetching the entry from a singleton - No key needed
			key = str(db.Key(skel.kindName, obj.getKey()))
		elif not key:
			logging.info("getEntry called without a valid key")
			return False

		if not isinstance(skel, SkeletonInstance):
			return False

		if "canView" in dir(obj):
			if not skel.fromDB(key):
				logging.info("getEntry: Entry %s not found" % (key,))
				return None
			if isinstance(obj, prototypes.singleton.Singleton):
				isAllowed = obj.canView()
			elif isinstance(obj, prototypes.tree.Tree):
				k = db.Key(key)
				if k.kind().endswith("_rootNode"):
					isAllowed = obj.canView("node", skel)
				else:
					isAllowed = obj.canView("leaf", skel)
			else:  # List and Hierarchies
				isAllowed = obj.canView(skel)
			if not isAllowed:
				logging.error("getEntry: Access to %s denied from canView" % (key,))
				return None
		elif "listFilter" in dir(obj):
			qry = skel.all().mergeExternalFilter({"key": str(key)})
			qry = obj.listFilter(qry)
			if not qry:
				logging.info("listFilter permits getting entry, returning None")
				return None

			skel = qry.getSkel()
			if not skel:
				return None

		else:  # No Access-Test for this module
			if not skel.fromDB(key):
				return None

		return render.collectSkelData(skel)

	return False


@jinjaGlobalFunction
def getHostUrl(render, forceSSL=False, *args, **kwargs):
	"""
	Jinja2 global: Retrieve hostname with protocol.

	:returns: Returns the hostname, including the currently used protocol, e.g: http://www.example.com
	:rtype: str
	"""
	url = currentRequest.get().request.url
	url = url[:url.find("/", url.find("://") + 5)]
	if forceSSL and url.startswith("http://"):
		url = "https://" + url[7:]
	return url


@jinjaGlobalFunction
def redirect(render, url):
	"""
	Jinja2 global: Redirect to another URL.

	:param url: URL to redirect to.
	:type url: str
	"""
	raise errors.Redirect(url)


@jinjaGlobalFunction
def getLanguage(render, resolveAlias=False):
	"""
	Jinja2 global: Returns the language used for this request.

	:param resolveAlias: If True, the function tries to resolve the current language
	using conf["viur.languageAliasMap"].
	:type resolveAlias: bool
	"""
	lang = currentLanguage.get()
	if resolveAlias and lang in conf["viur.languageAliasMap"]:
		lang = conf["viur.languageAliasMap"][lang]
	return lang


@jinjaGlobalFunction
def moduleName(render):
	"""
	Jinja2 global: Retrieve name of current module where this renderer is used within.

	:return: Returns the name of the current module, or empty string if there is no module set.
	"""
	if render.parent and "moduleName" in dir(render.parent):
		return render.parent.moduleName
	return ""


@jinjaGlobalFunction
def modulePath(render):
	"""
	Jinja2 global: Retrieve path of current module the renderer is used within.

	:return: Returns the path of the current module, or empty string if there is no module set.
	"""
	if render.parent and "modulePath" in dir(render.parent):
		return render.parent.modulePath
	return ""


@jinjaGlobalFunction
def getList(render, module, skel="viewSkel", _noEmptyFilter=False, *args, **kwargs):
	"""
	Jinja2 global: Fetches a list of entries which match the given filter criteria.

	:param module: Name of the module from which list should be fetched.
	:type module: str

	:param skel: Name of the skeleton that is used to fetching the list.
	:type skel: str

	:param _noEmptyFilter: If True, this function will not return any results if at least one
	parameter is an empty list. This is useful to prevent filtering (e.g. by key) not being
	performed because the list is empty.
	:type _noEmptyFilter: bool

	:returns: Returns a dict that contains the "skellist" and "cursor" information,
	or None on error case.
	:rtype: dict
	"""
	if not module in dir(conf["viur.mainApp"]):
		logging.error("Jinja2-Render can't fetch a list from an unknown module %s!" % module)
		return False
	caller = getattr(conf["viur.mainApp"], module)
	if not skel in dir(caller):
		logging.error("Jinja2-Render cannot fetch a list with an unknown skeleton %s!" % skel)
		return False
	if _noEmptyFilter:  # Test if any value of kwargs is an empty list
		if any([isinstance(x, list) and not len(x) for x in kwargs.values()]):
			return []
	query = getattr(caller, skel)().all()
	query.mergeExternalFilter(kwargs)
	if "listFilter" in dir(caller):
		query = caller.listFilter(query)
	if query is None:
		return None
	mylist = query.fetch()
	if mylist:
		for skel in mylist:
			skel.renderPreparation = render.renderBoneValue
	return mylist

@jinjaGlobalFunction
def getSecurityKey(render, **kwargs):
	"""
	Jinja2 global: Creates a new ViUR security key.
	"""
	return securitykey.create(**kwargs)


@jinjaGlobalFunction
def getStructure(render, module, skel="viewSkel", subSkel=None):
	"""
	Jinja2 global: Returns the skeleton structure instead of data for a module.

	:param module: Module from which the skeleton is retrieved.
	:type module: str

	:param skel: Name of the skeleton.
	:type skel: str

	:param subSkel: If set, return just that subskel instead of the whole skeleton
	:type subSkel: str or None
	"""
	if not module in dir(conf["viur.mainApp"]):
		return False

	obj = getattr(conf["viur.mainApp"], module)

	if skel in dir(obj):
		skel = getattr(obj, skel)()

		if isinstance(skel, SkeletonInstance) or isinstance(skel, RelSkel):
			if subSkel is not None:
				try:
					skel = skel.subSkel(subSkel)
				except Exception as e:
					logging.exception(e)
					return False

			return render.renderSkelStructure(skel)

	return False


@jinjaGlobalFunction
def requestParams(render):
	"""
	Jinja2 global: Allows for accessing the request-parameters from the template.

	These returned values are escaped, as users tend to use these in an unsafe manner.

	:returns: dict of parameter and values.
	:rtype: dict
	"""
	res = {}
	for k, v in currentRequest.get().kwargs.items():
		res[utils.escapeString(k)] = utils.escapeString(v)
	return res


@jinjaGlobalFunction
def updateURL(render, **kwargs):
	"""
	Jinja2 global: Constructs a new URL based on the current requests url.

	Given parameters are replaced if they exists in the current requests url, otherwise there appended.

	:returns: Returns a well-formed URL.
	:rtype: str
	"""
	tmpparams = {}
	tmpparams.update(currentRequest.get().kwargs)

	for key in list(tmpparams.keys()):
		if not key or key[0] == "_":
			del tmpparams[key]

	for key, value in list(kwargs.items()):
		if value is None:
			if key in tmpparams:
				del tmpparams[key]
		else:
			tmpparams[key] = value

	return "?" + urllib.parse.urlencode(tmpparams).replace("&", "&amp;")


@jinjaGlobalFilter
def fileSize(render, value, binary=False):
	"""
	Jinja2 filter: Format the value in an 'human-readable' file size (i.e. 13 kB, 4.1 MB, 102 Bytes, etc).
	Per default, decimal prefixes are used (Mega, Giga, etc.). When the second parameter is set to True,
	the binary prefixes are used (Mebi, Gibi).

	:param value: Value to be calculated.
	:type value: int | float

	:param binary: Decimal prefixes behavior
	:type binary: bool

	:returns: The formatted file size string in human readable format.
	:type: str
	"""
	bytes = float(value)
	base = binary and 1024 or 1000

	prefixes = [
		(binary and 'KiB' or 'kB'),
		(binary and 'MiB' or 'MB'),
		(binary and 'GiB' or 'GB'),
		(binary and 'TiB' or 'TB'),
		(binary and 'PiB' or 'PB'),
		(binary and 'EiB' or 'EB'),
		(binary and 'ZiB' or 'ZB'),
		(binary and 'YiB' or 'YB')
	]

	if bytes == 1:
		return '1 Byte'
	elif bytes < base:
		return '%d Bytes' % bytes

	unit = 0
	prefix = ""

	for i, prefix in enumerate(prefixes):
		unit = base ** (i + 2)
		if bytes < unit:
			break

	return '%.1f %s' % ((base * bytes / unit), prefix)


@jinjaGlobalFilter
def urlencode(render, val):
	"""
	Jinja2 filter: Make a string URL-safe.

	:param val: String to be quoted.
	:type val: str

	:returns: Quoted string.
	:rtype: str
	"""

	# quote_plus fails if val is None
	if not val:
		return ""

	if isinstance(val, str):
		val = val.encode("UTF-8")

	return urllib.parse.quote_plus(val)


'''
This has been disabled until we are sure
	a) what use-cases it has
	b) how it's best implemented
	c) doesn't introduce any XSS vulnerability
  - TS 13.03.2016
@jinjaGlobalFilter
def className(render, s):
	"""
	Jinja2 filter: Converts a URL or name into a CSS-class name, by replacing slashes by underscores.
	Example call could be```{{self|string|toClassName}}```.

	:param s: The string to be converted, probably ``self|string`` in the Jinja2 template.
	:type s: str

	:return: CSS class name.
	:rtype: str
	"""
	l = re.findall('\'([^\']*)\'', str(s))
	if l:
		l = set(re.split(r'/|_', l[0].replace(".html", "")))
		return " ".join(l)

	return ""
'''


@jinjaGlobalFilter
def shortKey(render, val):
	"""
	Jinja2 filter: Make a shortkey from an entity-key.

	:param val: Entity-key as string.
	:type val: str

	:returns: Shortkey on success, None on error.
	:rtype: str
	"""

	try:
		k = db.Key(encoded=str(val))
		return k.id_or_name()
	except:
		return None


@jinjaGlobalFunction
def renderEditBone(render, skel, boneName):
	if not isinstance(skel, dict) or not all([x in skel for x in ["errors", "structure", "value"]]):
		raise ValueError("This does not look like an editable Skeleton!")

	boneParams = skel["structure"].get(boneName)

	if not boneParams:
		raise ValueError("Bone %s is not part of that skeleton" % boneName)

	if not boneParams["visible"]:
		fileName = "editform_bone_hidden"
	else:
		fileName = "editform_bone_" + boneParams["type"]

	while fileName:
		try:
			fn = render.getTemplateFileName(fileName)
			break

		except errors.NotFound:
			if "." in fileName:
				fileName, unused = fileName.rsplit(".", 1)
			else:
				fn = render.getTemplateFileName("editform_bone_bone")
				break

	tpl = render.getEnv().get_template(fn)

	return tpl.render(boneName=boneName, boneParams=boneParams, boneValue=skel["value"].get(boneName, None))


@jinjaGlobalFunction
def renderEditForm(render, skel, ignore=None, hide=None):
	if not isinstance(skel, dict) or not all([x in skel.keys() for x in ["errors", "structure", "value"]]):
		raise ValueError("This does not look like an editable Skeleton!")

	res = u""

	sectionTpl = render.getEnv().get_template(render.getTemplateFileName("editform_category"))
	rowTpl = render.getEnv().get_template(render.getTemplateFileName("editform_row"))
	sections = OrderedDict()
	for boneName, boneParams in skel["structure"].items():
		category = str("server.render.html.default_category")
		if "params" in boneParams and isinstance(boneParams["params"], dict):
			category = boneParams["params"].get("category", category)
		if not category in sections:
			sections[category] = []

		sections[category].append((boneName, boneParams))

	for category, boneList in sections.items():
		allReadOnly = True
		allHidden = True
		categoryContent = u""

		for boneName, boneParams in boneList:
			if ignore and boneName in ignore:
				continue

			boneWasInvalid = isinstance(skel["errors"], dict) and boneName in skel["errors"].keys()

			if hide and boneName in hide:
				boneParams["visible"] = False

			if not boneParams["readOnly"]:
				allReadOnly = False

			if boneParams["visible"]:
				allHidden = False

			editWidget = renderEditBone(render, skel, boneName)
			categoryContent += rowTpl.render(boneName=boneName,
											 boneParams=boneParams,
											 boneWasInvalid=boneWasInvalid,
											 editWidget=editWidget)

		res += sectionTpl.render(categoryName=category,
								 categoryClassName="".join([x for x in category if x in string.ascii_letters]),
								 categoryContent=categoryContent,
								 allReadOnly=allReadOnly,
								 allHidden=allHidden)

	return res


@jinjaGlobalFunction
def embedSvg(self, name):
	if any([x in name for x in ["..", "~", "/"]]):
		return u""
	try:
		return open(os.path.join(os.getcwd(), "html", "embedsvg", name + ".svg"), "rb").read().decode("UTF-8")
	except Exception as e:
		logging.exception(e)
		return ""


@jinjaGlobalFunction
def downloadUrlFor(render, fileObj, derived=None, expires=timedelta(hours=1)):
	if not isinstance(fileObj, (SkeletonInstance, dict)) or "dlkey" not in fileObj or "name" not in fileObj:
		return None
	if derived and ("derived" not in fileObj or not isinstance(fileObj["derived"], dict)):
		return None
	if derived:
		return utils.downloadUrlFor(folder=fileObj["dlkey"], fileName=derived, derived=True, expires=expires)
	else:
		return utils.downloadUrlFor(folder=fileObj["dlkey"], fileName=fileObj["name"], derived=False, expires=expires)

@jinjaGlobalFunction
def srcSetFor(render, fileObj, expires=timedelta(hours=1)):
	if not isinstance(fileObj, (SkeletonInstance, dict)) or not "dlkey" in fileObj or "derived" not in fileObj:
		return None
	if not isinstance(fileObj["derived"], dict):
		return ""
	resList = []
	for fileName, deriviation in fileObj["derived"].items():
		params = deriviation["params"]
		if params.get("group") == "srcset":
			resList.append("%s %sw" % (utils.downloadUrlFor(fileObj["dlkey"], fileName, True, expires), params["width"]))
	return ", ".join(resList)

@jinjaGlobalFunction
def seoUrlForEntry(render, *args, **kwargs):
	return utils.seoUrlToEntry(*args, **kwargs)

@jinjaGlobalFunction
def seoUrlToFunction(render, *args, **kwargs):
	return utils.seoUrlToFunction(*args, **kwargs)

