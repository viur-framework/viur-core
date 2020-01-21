# -*- coding: utf-8 -*-
from . import utils as jinjaUtils
from .wrap import ListWrapper, SkelListWrapper

from viur.core import utils, request, errors, securitykey
from viur.core.skeleton import Skeleton, BaseSkeleton, RefSkel, skeletonByKind
from viur.core.bones import *

from collections import OrderedDict
from jinja2 import Environment, FileSystemLoader, ChoiceLoader
from viur.core.i18n import translate
import os, logging, codecs
from collections import namedtuple

KeyValueWrapper = namedtuple("KeyValueWrapper", ["key", "descr"])

class Render(object):
	"""
		The core jinja2 render.

		This is the bridge between your ViUR modules and your templates.
		First, the default jinja2-api is exposed to your templates. See http://jinja.pocoo.org/ for
		more information. Second, we'll pass data das global variables to templates depending on the
		current action.

			- For list() we'll pass `skellist` - a :py:class:`server.render.jinja2.default.SkelListWrapper` instance
			- For view(): skel - a dictionary with values from the skeleton prepared for use inside html
			- For add()/edit: a dictionary as `skel` with `values`, `structure` and `errors` as keys.

		Third, a bunch of global filters (like urlencode) and functions (getEntry, ..) are available  to templates.

		See the ViUR Documentation for more information about functions and data available to jinja2 templates.

		Its possible for modules to extend the list of filters/functions available to templates by defining
		a function called `jinjaEnv`. Its called from the render when the environment is first created and
		can extend/override the functionality exposed to templates.

	"""
	listTemplate = "list"
	viewTemplate = "view"
	addTemplate = "add"
	editTemplate = "edit"
	addSuccessTemplate = "add_success"
	editSuccessTemplate = "edit_success"
	deleteSuccessTemplate = "delete_success"
	listRepositoriesTemplate = "list_repositories"
	listRootNodeContentsTemplate = "list_rootNode_contents"
	addDirSuccessTemplate = "add_dir_success"
	renameSuccessTemplate = "rename_success"
	copySuccessTemplate = "copy_success"

	reparentSuccessTemplate = "reparent_success"
	setIndexSuccessTemplate = "setindex_success"
	cloneSuccessTemplate = "clone_success"

	__haveEnvImported_ = False

	def __init__(self, parent=None, *args, **kwargs):
		super(Render, self).__init__(*args, **kwargs)
		if not Render.__haveEnvImported_:
			# We defer loading our plugins to this point to avoid circular imports
			from . import env
			Render.__haveEnvImported_ = True
		self.parent = parent

	def getTemplateFileName(self, template, ignoreStyle=False):
		"""
			Returns the filename of the template.

			This function decides in which language and which style a given template is rendered.
			The style is provided as get-parameters for special-case templates that differ from
			their usual way.

			It is advised to override this function in case that
			:func:`server.render.jinja2.default.Render.getLoaders` is redefined.

			:param template: The basename of the template to use.
			:type template: str

			:param ignoreStyle: Ignore any maybe given style hints.
			:type ignoreStyle: bool

			:returns: Filename of the template
			:rtype: str
		"""
		validChars = "abcdefghijklmnopqrstuvwxyz1234567890-"
		if "htmlpath" in dir(self):
			htmlpath = self.htmlpath
		else:
			htmlpath = "html"
		if not ignoreStyle \
				and "style" in request.current.get().kwargs \
				and all([x in validChars for x in request.current.get().kwargs["style"].lower()]):
			stylePostfix = "_" + request.current.get().kwargs["style"]
		else:
			stylePostfix = ""
		lang = request.current.get().language  # session.current.getLanguage()
		fnames = [template + stylePostfix + ".html", template + ".html"]
		if lang:
			fnames = [os.path.join(lang, template + stylePostfix + ".html"),
					  template + stylePostfix + ".html",
					  os.path.join(lang, template + ".html"),
					  template + ".html"]
		for fn in fnames:  # check subfolders
			prefix = template.split("_")[0]
			if os.path.isfile(os.path.join(os.getcwd(), htmlpath, prefix, fn)):
				return ("%s/%s" % (prefix, fn))
		for fn in fnames:  # Check the templatefolder of the application
			if os.path.isfile(os.path.join(os.getcwd(), htmlpath, fn)):
				return fn
		for fn in fnames:  # Check the fallback
			if os.path.isfile(os.path.join(os.getcwd(), "viur", "server", "template", fn)):
				return fn
		raise errors.NotFound("Template %s not found." % template)

	def getLoaders(self):
		"""
			Return the list of Jinja2 loaders which should be used.

			May be overridden to provide an alternative loader
			(e.g. for fetching templates from the datastore).
		"""
		if "htmlpath" in dir(self):
			htmlpath = self.htmlpath
		else:
			htmlpath = "html/"

		return ChoiceLoader([FileSystemLoader(htmlpath), FileSystemLoader("viur/server/template/")])

	def renderBoneStructure(self, bone):
		"""
		Renders the structure of a bone.

		This function is used by :func:`renderSkelStructure`.
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
			"readOnly": bone.readOnly
		}

		if bone.type == "relational" or bone.type.startswith("relational."):
			if isinstance(bone, hierarchyBone):
				boneType = "hierarchy"
			elif isinstance(bone, treeItemBone):
				boneType = "treeitem"
			else:
				boneType = "relational"

			ret.update({
				"type": bone.type,
				"module": bone.module,
				"multiple": bone.multiple,
				"format": bone.format,
				"using": self.renderSkelStructure(bone.using()) if bone.using else None,
				"relskel": self.renderSkelStructure(RefSkel.fromSkel(skeletonByKind(bone.kind), *bone.refKeys))
			})

		elif bone.type == "select" or bone.type.startswith("select."):
			ret.update({
				"values": OrderedDict([(k, _(v)) for (k, v) in bone.values.items()]),
				"multiple": bone.multiple
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
				"languages": bone.languages,
				"multiple": bone.multiple
			})
		elif bone.type == "captcha" or bone.type.startswith("captcha."):
			ret.update({
				"publicKey": bone.publicKey,
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
		res = OrderedDict()

		for key, bone in skel.items():
			if "__" in key or not isinstance(bone, baseBone):
				continue

			res[key] = self.renderBoneStructure(bone)

			if key in skel.errors:
				res[key]["error"] = skel.errors[key]
			else:
				res[key]["error"] = None

		return res

	def renderBoneValue(self, bone, skel, key, boneValue):
		"""
		Renders the value of a bone.

		This function is used by :func:`collectSkelData`.
		It can be overridden and super-called from a custom renderer.

		:param bone: The bone which value should be rendered.
		:type bone: Any bone that inherits from :class:`server.bones.base.baseBone`.

		:return: A dict containing the rendered attributes.
		:rtype: dict
		"""
		if bone.type == "select" or bone.type.startswith("select."):
			skelValue = boneValue
			if isinstance(skelValue, list):
				return [
					KeyValueWrapper(val, bone.values[val]) if val in bone.values else KeyValueWrapper(val, str(val))
					for val in skelValue
				]
			elif skelValue in bone.values:
				return KeyValueWrapper(skelValue, bone.values[skelValue])
			return KeyValueWrapper(skelValue, str(skelValue))
		elif bone.type == "relational" or bone.type.startswith("relational."):
			if isinstance(boneValue, list):
				tmpList = []
				for k in boneValue:
					refSkel = bone._refSkelCache
					refSkel.setValuesCache(k["dest"])
					if bone.using is None:
						tmpList.append(self.collectSkelData(refSkel))
					else:
						usingSkel = bone._usingSkelCache
						if k["rel"]:
							usingSkel.setValuesCache(k["rel"])
							usingData = self.collectSkelData(usingSkel)
						else:
							usingData = None
						tmpList.append({
							"dest": self.collectSkelData(refSkel),
							"rel": usingData
						})
				return tmpList
			elif isinstance(boneValue, dict):
				refSkel = bone._refSkelCache
				refSkel.setValuesCache(boneValue["dest"])
				refSkel.renderPreparation = self.renderBoneValue
				if bone.using is None:
					return refSkel
				else:
					usingSkel = bone._usingSkelCache
					if boneValue["rel"]:
						usingSkel.setValuesCache(boneValue["rel"])
						usingData = self.collectSkelData(usingSkel)
					else:
						usingData = None

					return {
						"dest": self.collectSkelData(refSkel),
						"rel": usingData
					}
		elif bone.type == "record" or bone.type.startswith("record."):
			usingSkel = bone._usingSkelCache
			value = boneValue
			if isinstance(value, list):
				ret = []
				for entry in value:
					usingSkel.setValuesCache(entry)
					ret.append(self.collectSkelData(usingSkel))

				return ret
			elif isinstance(value, dict):
				usingSkel.setValuesCache(value)
				return self.collectSkelData(usingSkel)
		elif bone.type == "key":
			return boneValue.id_or_name if boneValue else None
		else:
			return boneValue
		return None

	def collectSkelData(self, skel):
		"""
			Prepares values of one :class:`server.db.skeleton.Skeleton` or a list of skeletons for output.

			:param skel: Skeleton which contents will be processed.
			:type skel: server.db.skeleton.Skeleton

			:returns: A dictionary or list of dictionaries.
			:rtype: dict | list
		"""
		# logging.error("collectSkelData %s", skel)
		if isinstance(skel, list):
			return [self.collectSkelData(x) for x in skel]
		res = {}
		for key, bone in skel.items():
			val = self.renderBoneValue(bone, skel, key, skel[key])
			res[key] = val
			if isinstance(res[key], list):
				res[key] = ListWrapper(res[key])
		return res

	def add(self, skel, tpl=None, params=None, *args, **kwargs):
		"""
			Renders a page for adding an entry.

			The template must construct the HTML-form on itself; the required information
			are passed via skel.structure, skel.value and skel.errors.

			A jinja2-macro, which builds such kind of forms, is shipped with the server.

			Any data in \*\*kwargs is passed unmodified to the template.

			:param skel: Skeleton of the entry which should be created.
			:type skel: server.db.skeleton.Skeleton

			:param tpl: Name of a different template, which should be used instead of the default one.
			:type tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl and "addTemplate" in dir(self.parent):
			tpl = self.parent.addTemplate

		tpl = tpl or self.addTemplate
		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		skel = skel.clone()  # Fixme!
		skeybone = baseBone(descr="SecurityKey", readOnly=True, visible=False)
		skel.skey = skeybone
		skel["skey"] = securitykey.create()

		if "nomissing" in request.current.get().kwargs and request.current.get().kwargs["nomissing"] == "1":
			if isinstance(skel, BaseSkeleton):
				super(BaseSkeleton, skel).__setattr__("errors", {})

		return template.render(skel={"structure": self.renderSkelStructure(skel),
									 "errors": skel.errors,
									 "value": self.collectSkelData(skel)},
							   params=params, **kwargs)

	def edit(self, skel, tpl=None, params=None, **kwargs):
		"""
			Renders a page for modifying an entry.

			The template must construct the HTML-form on itself; the required information
			are passed via skel.structure, skel.value and skel.errors.

			A jinja2-macro, which builds such kind of forms, is shipped with the server.

			Any data in \*\*kwargs is passed unmodified to the template.

			:param skel: Skeleton of the entry which should be modified.
			:type skel: server.db.skeleton.Skeleton

			:param tpl: Name of a different template, which should be used instead of the default one.
			:type tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl and "editTemplate" in dir(self.parent):
			tpl = self.parent.editTemplate

		tpl = tpl or self.editTemplate
		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		skel = skel.clone()  # Fixme!
		skeybone = baseBone(descr="SecurityKey", readOnly=True, visible=False)
		skel.skey = skeybone
		skel["skey"] = securitykey.create()

		if "nomissing" in request.current.get().kwargs and request.current.get().kwargs["nomissing"] == "1":
			if isinstance(skel, BaseSkeleton):
				super(BaseSkeleton, skel).__setattr__("errors", {})

		return template.render(skel={"structure": self.renderSkelStructure(skel),
									 "errors": skel.errors,
									 "value": self.collectSkelData(skel)},
							   params=params, **kwargs)

	def addItemSuccess(self, skel, tpl=None, params=None, *args, **kwargs):
		"""
			Renders a page, informing that the entry has been successfully created.

			:param skel: Skeleton which contains the data of the new entity
			:type skel: server.db.skeleton.Skeleton

			:param tpl: Name of a different template, which should be used instead of the default one.
			:type tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl:
			if "addSuccessTemplate" in dir(self.parent):
				tpl = self.parent.addSuccessTemplate
			else:
				tpl = self.addSuccessTemplate

		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		res = self.collectSkelData(skel)

		return template.render({"skel": res}, params=params, **kwargs)

	def editItemSuccess(self, skel, tpl=None, params=None, *args, **kwargs):
		"""
			Renders a page, informing that the entry has been successfully modified.

			:param skel: Skeleton which contains the data of the modified entity
			:type skel: server.db.skeleton.Skeleton

			:param tpl: Name of a different template, which should be used instead of the default one.
			:type tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl:
			if "editSuccessTemplate" in dir(self.parent):
				tpl = self.parent.editSuccessTemplate
			else:
				tpl = self.editSuccessTemplate

		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		res = self.collectSkelData(skel)
		return template.render(skel=res, params=params, **kwargs)

	def deleteSuccess(self, skel, tpl=None, params=None, *args, **kwargs):
		"""
			Renders a page, informing that the entry has been successfully deleted.

			The provided parameters depend on the application calling this:
			List and Hierarchy pass the id of the deleted entry, while Tree passes
			the rootNode and path.

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:param tpl: Name of a different template, which should be used instead of the default one.
			:type tpl: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl:
			if "deleteSuccessTemplate" in dir(self.parent):
				tpl = self.parent.deleteSuccessTemplate
			else:
				tpl = self.deleteSuccessTemplate

		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		return template.render(params=params, **kwargs)

	def list(self, skellist, tpl=None, params=None, **kwargs):
		"""
			Renders a list of entries.

			Any data in \*\*kwargs is passed unmodified to the template.

			:param skellist: List of Skeletons with entries to display.
			:type skellist: server.db.skeleton.SkelList

			:param tpl: Name of a different template, which should be used instead of the default one.
			:param: tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl and "listTemplate" in dir(self.parent):
			tpl = self.parent.listTemplate
		tpl = tpl or self.listTemplate
		try:
			fn = self.getTemplateFileName(tpl)
		except errors.HTTPException as e:  # Not found - try default fallbacks FIXME: !!!
			tpl = "list"
		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		# resList = []
		# for skel in skellist:
		#	resList.append(self.collectSkelData(skel))
		skellist.renderPreparation = self.renderBoneValue
		return template.render(skellist=skellist, params=params, **kwargs)  # SkelListWrapper(resList, skellist)

	def listRootNodes(self, repos, tpl=None, params=None, **kwargs):
		"""
			Renders a list of available repositories.

			:param repos: List of repositories (dict with "key"=>Repo-Key and "name"=>Repo-Name)
			:type repos: list

			:param tpl: Name of a different template, which should be used instead of the default one.
			:param: tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if "listRepositoriesTemplate" in dir(self.parent):
			tpl = tpl or self.parent.listTemplate
		if not tpl:
			tpl = self.listRepositoriesTemplate
		try:
			fn = self.getTemplateFileName(tpl)
		except errors.HTTPException as e:  # Not found - try default fallbacks FIXME: !!!
			tpl = "list"
		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		return template.render(repos=repos, params=params, **kwargs)

	def view(self, skel, tpl=None, params=None, **kwargs):
		"""
			Renders a single entry.

			Any data in \*\*kwargs is passed unmodified to the template.

			:param skel: Skeleton to be displayed.
			:type skellist: server.db.skeleton.Skeleton

			:param tpl: Name of a different template, which should be used instead of the default one.
			:param: tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl and "viewTemplate" in dir(self.parent):
			tpl = self.parent.viewTemplate

		tpl = tpl or self.viewTemplate
		template = self.getEnv().get_template(self.getTemplateFileName(tpl))

		if isinstance(skel, Skeleton):
			# res = self.collectSkelData(skel)
			skel.renderPreparation = self.renderBoneValue
		return template.render(skel=skel, params=params, **kwargs)

	## Extended functionality for the Tree-Application ##
	def listRootNodeContents(self, subdirs, entries, tpl=None, params=None, **kwargs):
		"""
			Renders the contents of a given RootNode.

			This differs from list(), as one level in the tree-application may contains two different
			child-types: Entries and folders.

			:param subdirs: List of (sub-)directories on the current level
			:type repos: list

			:param entries: List of entries of the current level
			:type entries: server.db.skeleton.SkelList

			:param tpl: Name of a different template, which should be used instead of the default one
			:param: tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if "listRootNodeContentsTemplate" in dir(self.parent):
			tpl = tpl or self.parent.listRootNodeContentsTemplate
		else:
			tpl = tpl or self.listRootNodeContentsTemplate
		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		return template.render(subdirs=subdirs, entries=[self.collectSkelData(x) for x in entries], params=params,
							   **kwargs)

	def addDirSuccess(self, rootNode, path, dirname, params=None, *args, **kwargs):
		"""
			Renders a page, informing that the directory has been successfully created.

			:param rootNode: RootNode-key in which the directory has been created
			:type rootNode: str

			:param path: Path in which the directory has been created
			:type path: str

			:param dirname: Name of the newly created directory
			:type dirname: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""

		tpl = self.addDirSuccessTemplate
		if "addDirSuccessTemplate" in dir(self.parent):
			tpl = self.parent.addDirSuccessTemplate
		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		return template.render(rootNode=rootNode, path=path, dirname=dirname, params=params)

	def renameSuccess(self, rootNode, path, src, dest, params=None, *args, **kwargs):
		"""
			Renders a page, informing that the entry has been successfully renamed.

			:param rootNode: RootNode-key in which the entry has been renamed
			:type rootNode: str

			:param path: Path in which the entry has been renamed
			:type path: str

			:param src: Old name of the entry
			:type src: str

			:param dest: New name of the entry
			:type dest: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		tpl = self.renameSuccessTemplate
		if "renameSuccessTemplate" in dir(self.parent):
			tpl = self.parent.renameSuccessTemplate
		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		return template.render(rootNode=rootNode, path=path, src=src, dest=dest, params=params)

	def copySuccess(self, srcrepo, srcpath, name, destrepo, destpath, type, deleteold, params=None, *args, **kwargs):
		"""
			Renders a page, informing that an entry has been successfully copied/moved.

			:param srcrepo: RootNode-key from which has been copied/moved
			:type srcrepo: str

			:param srcpath: Path from which the entry has been copied/moved
			:type srcpath: str

			:param name: Name of the entry which has been copied/moved
			:type name: str

			:param destrepo: RootNode-key to which has been copied/moved
			:type destrepo: str

			:param destpath: Path to which the entries has been copied/moved
			:type destpath: str

			:param type: "entry": Copy/Move an entry, everything else: Copy/Move an directory
			:type type: str

			:param deleteold: "0": Copy, "1": Move
			:type deleteold: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		tpl = self.copySuccessTemplate
		if "copySuccessTemplate" in dir(self.parent):
			tpl = self.parent.copySuccessTemplate
		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		return template.render(srcrepo=srcrepo, srcpath=srcpath, name=name, destrepo=destrepo, destpath=destpath,
							   type=type, deleteold=deleteold, params=params)

	def reparentSuccess(self, obj, tpl=None, params=None, **kwargs):
		"""
			Renders a page informing that the item was successfully moved.

			:param obj: ndb.Expando instance of the item that was moved.
			:type obj: ndb.Expando

			:param tpl: Name of a different template, which should be used instead of the default one
			:type tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object
		"""
		if not tpl:
			if "reparentSuccessTemplate" in dir(self.parent):
				tpl = self.parent.reparentSuccessTemplate
			else:
				tpl = self.reparentSuccessTemplate

		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		return template.render(repoObj=obj, params=params, **kwargs)

	def setIndexSuccess(self, obj, tpl=None, params=None, *args, **kwargs):
		"""
			Renders a page informing that the items sortindex was successfully changed.

			:param obj: ndb.Expando instance of the item that was changed
			:type obj: ndb.Expando

			:param tpl: Name of a different template, which should be used instead of the default one
			:type tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl:
			if "setIndexSuccessTemplate" in dir(self.parent):
				tpl = self.parent.setIndexSuccessTemplate
			else:
				tpl = self.setIndexSuccessTemplate

		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		return template.render(skel=obj, repoObj=obj, params=params, **kwargs)

	def cloneSuccess(self, tpl=None, params=None, *args, **kwargs):
		"""
			Renders a page informing that the items sortindex was successfully changed.

			:param obj: ndb.Expando instance of the item that was changed
			:type obj: ndb.Expando

			:param tpl: Name of a different template, which should be used instead of the default one
			:type tpl: str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl:
			if "cloneSuccessTemplate" in dir(self.parent):
				tpl = self.parent.cloneSuccessTemplate
			else:
				tpl = self.cloneSuccessTemplate

		template = self.getEnv().get_template(self.getTemplateFileName(tpl))
		return template.render(params=params, **kwargs)

	def renderEmail(self, skel, tpl, dests, params=None, **kwargs):
		"""
			Renders an email.

			:param skel: Skeleton or dict which data to supply to the template.
			:type skel: server.db.skeleton.Skeleton | dict

			:param tpl: Name of the email-template to use. If this string is longer than 100 characters,
				this string is interpreted as the template contents instead of its filename.
			:type tpl: str

			:param dests: Destination recipients.
			:type dests: list | str

			:param params: Optional data that will be passed unmodified to the template
			:type params: object

			:return: Returns a tuple consisting of email header and body.
			:rtype: str, str
		"""
		headers = {}
		user = utils.getCurrentUser()
		if isinstance(skel, BaseSkeleton):
			res = self.collectSkelData(skel)
		elif isinstance(skel, list) and all([isinstance(x, BaseSkeleton) for x in skel]):
			res = [self.collectSkelData(x) for x in skel]
		else:
			res = skel
		if len(tpl) < 101:
			try:
				template = self.getEnv().from_string(codecs.open("emails/" + tpl + ".email", "r", "utf-8").read())
			except Exception as err:
				logging.exception(err)
				template = self.getEnv().get_template(tpl + ".email")
		else:
			template = self.getEnv().from_string(tpl)
		data = template.render(skel=res, dests=dests, user=user, params=params, **kwargs)
		body = False
		lineCount = 0
		for line in data.splitlines():
			if lineCount > 3 and body is False:
				body = "\n\n"
			if body != False:
				body += line + "\n"
			else:
				if line.lower().startswith("from:"):
					headers["from"] = line[len("from:"):]
				elif line.lower().startswith("subject:"):
					headers["subject"] = line[len("subject:"):]
				elif line.lower().startswith("references:"):
					headers["references"] = line[len("references:"):]
				else:
					body = "\n\n"
					body += line
			lineCount += 1
		return (headers, body)

	def getEnv(self):
		"""
			Constucts the Jinja2 environment.

			If an application specifies an jinja2Env function, this function
			can alter the environment before its used to parse any template.

			:returns: Extended Jinja2 environment.
			:rtype: jinja2.Environment
		"""

		def mkLambda(func, s):
			return lambda *args, **kwargs: func(s, *args, **kwargs)

		if not "env" in dir(self):
			loaders = self.getLoaders()
			self.env = Environment(loader=loaders, extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])

			# Translation remains global
			self.env.globals["_"] = lambda x, *args, **kwargs: str(x)  # FIXME !translate
			self.env.filters["tr"] = lambda x, *args, **kwargs: str(x)  # FIXME !translate

			# Import functions.
			for name, func in jinjaUtils.getGlobalFunctions().items():
				self.env.globals[name] = mkLambda(func, self)

			# Import filters.
			for name, func in jinjaUtils.getGlobalFilters().items():
				self.env.filters[name] = mkLambda(func, self)

			# Import extensions.
			for ext in jinjaUtils.getGlobalExtensions():
				self.env.add_extension(ext)

			# Import module-specific environment, if available.
			if "jinjaEnv" in dir(self.parent):
				self.env = self.parent.jinjaEnv(self.env)

		return self.env
