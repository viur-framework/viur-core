# -*- coding: utf-8 -*-

import utils as jinjaUtils
from server import conf, bones, utils, request, session, conf, errors, securitykey, prototypes
from server.skeleton import Skeleton, RelSkel
from server.bones import *

from collections import OrderedDict
from jinja2 import Environment, FileSystemLoader, ChoiceLoader

import os, logging, codecs

class ListWrapper( list ):
	"""
		Monkey-Patching for lists.
		Allows collecting sub-properties by using []
		Example: [ {"key":"1"}, {"key":"2"} ]["key"] --> ["1","2"]
	"""
	def __init__( self, src ):
		"""
			Initializes this wrapper by copying the values from src
		"""
		self.extend( src )
	
	def __getitem__( self, key ):
		if isinstance( key, int ):
			return( super( ListWrapper, self ).__getitem__( key ) )
		res = []
		for obj in self:
			if isinstance( obj, dict ) and key in obj.keys():
				res.append( obj[ key ] )
			elif key in dir( obj ):
				res.append( getattr( obj, key ) )
		return( ListWrapper(res) )

class SkelListWrapper( ListWrapper ):
	"""
		Like ListWrapper, but takes the additional properties
		of skellist into account - namely cursor and customQueryInfo.
	"""
	def __init__( self, src ):
		super( SkelListWrapper, self ).__init__( src )
		self.cursor = src.cursor
		self.customQueryInfo = src.customQueryInfo

class Render( object ):
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
	
	class KeyValueWrapper:
		"""
			This holds one Key-Value pair for
			selectOne/selectMulti Bones.

			It allows to directly treat the key as string,
			but still makes the translated description of that
			key available.
		"""
		def __init__( self, key, descr ):
			self.key = key
			self.descr = _( descr )

		def __str__( self ):
			return( unicode( self.key ) )
		
		def __repr__( self ):
			return( unicode( self.key ) )
		
		def __eq__( self, other ):
			return( unicode( self ) == unicode( other ) )
		
		def __lt__( self, other ):
			return( unicode( self ) < unicode( other ) )

		def __gt__( self, other ):
			return( unicode( self ) > unicode( other ) )

		def __le__( self, other ):
			return( unicode( self ) <= unicode( other ) )

		def __ge__( self, other ):
			return( unicode( self ) >= unicode( other ) )

		def __trunc__( self ):
			return( self.key.__trunc__() )

	def __init__(self, parent=None, *args, **kwargs ):
		super( Render, self ).__init__(*args, **kwargs)
		if not Render.__haveEnvImported_:
			# We defer loading our plugins to this point to avoid circular imports
			import env
			Render.__haveEnvImported_ = True
		self.parent = parent

	
	def getTemplateFileName( self, template, ignoreStyle=False ):
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
		if "htmlpath" in dir( self ):
			htmlpath = self.htmlpath
		else:
			htmlpath = "html"
		if not ignoreStyle\
			and "style" in list( request.current.get().kwargs.keys())\
			and all( [ x in validChars for x in request.current.get().kwargs["style"].lower() ] ):
				stylePostfix = "_"+request.current.get().kwargs["style"]
		else:
			stylePostfix = ""
		lang = request.current.get().language #session.current.getLanguage()
		fnames = [ template+stylePostfix+".html", template+".html" ]
		if lang:
			fnames = [ 	os.path.join(  lang, template+stylePostfix+".html"),
						template+stylePostfix+".html", 
						os.path.join(  lang, template+".html"), 
						template+".html" ]
		for fn in fnames: #check subfolders
			prefix = template.split("_")[0]
			if os.path.isfile(os.path.join(os.getcwd(), "html", prefix, fn)):
				return ( "%s/%s" % (prefix, fn ) )
		for fn in fnames: #Check the templatefolder of the application
			if os.path.isfile( os.path.join( os.getcwd(), htmlpath, fn ) ):
				self.checkForOldLinePrefix( os.path.join( os.getcwd(), htmlpath, fn ) )
				return( fn )
		for fn in fnames: #Check the fallback
			if os.path.isfile( os.path.join( os.getcwd(), "server", "template", fn ) ):
				self.checkForOldLinePrefix( os.path.join( os.getcwd(), "server", "template", fn ) )
				return( fn )
		raise errors.NotFound( "Template %s not found." % template )

	def checkForOldLinePrefix(self, fn):
		"""
			This method checks the given template for lines starting with "##" - the old, now unsupported
			Line-Prefix. Bail out if such prefixes are used. This is a temporary safety measure; will be
			removed after 01.05.2017.
		:param fn: The filename to check
		:return:
		"""
		if not "_safeTemplatesCache" in dir( self ):
			self._safeTemplatesCache = [] #Scan templates at most once per instance
		if fn in self._safeTemplatesCache:
			return #This template has already been checked and looks okay
		tplData = open( fn, "r" ).read()
		for l in tplData.splitlines():
			if l.strip(" \t").startswith("##"):
				raise SyntaxError("Template %s contains unsupported Line-Markers (##)" % fn )
		self._safeTemplatesCache.append( fn )
		return

	def getLoaders(self):
		"""
			Return the list of Jinja2 loaders which should be used.

			May be overridden to provide an alternative loader
			(e.g. for fetching templates from the datastore).
		"""
		if "htmlpath" in dir( self ):
			htmlpath = self.htmlpath
		else:
			htmlpath = "html/"
		return( ChoiceLoader( [FileSystemLoader( htmlpath ), FileSystemLoader( "server/template/" )] ) )


	def renderSkelStructure(self, skel):
		"""
			Dumps the structure of a :class:`server.db.skeleton.Skeleton`.

			:param skel: Skeleton which structure will be processed.
			:type skel: server.db.skeleton.Skeleton

			:returns: The rendered dictionary.
			:rtype: dict
		"""
		res = OrderedDict()
		for key, _bone in skel.items():
			if "__" not in key:
				if( isinstance( _bone, bones.baseBone ) ):
					res[ key ] = {	"descr":  _(_bone.descr ), 
							"type": _bone.type,
							"required":_bone.required,
							"params":_bone.params,
							"visible": _bone.visible,
							"readOnly": _bone.readOnly
							}
					if key in skel.errors.keys():
						res[ key ][ "error" ] = skel.errors[ key ]
					else:
						res[ key ][ "error" ] = None
					if isinstance( _bone, bones.relationalBone ):
						if isinstance( _bone, bones.hierarchyBone ):
							boneType = "hierarchy."+_bone.type
						elif isinstance( _bone, bones.treeItemBone ):
							boneType = "treeitem."+_bone.type
						else:
							boneType = "relational."+_bone.type
						res[key]["type"] = boneType
						res[key]["module"] = _bone.module
						res[key]["multiple"]=_bone.multiple
						res[key]["format"] = _bone.format
					if( isinstance( _bone, bones.selectOneBone ) or isinstance( _bone, bones.selectMultiBone ) ):
						res[key]["values"] =  _bone.values
					if( isinstance( _bone, bones.dateBone ) ):
						res[key]["time"] = _bone.time
						res[key]["date"] = _bone.date
					if( isinstance( _bone, bones.numericBone )):
						res[key]["precision"] = _bone.precision
						res[key]["min"] = _bone.min
						res[key]["max"] = _bone.max
					if( isinstance( _bone, bones.textBone ) ):
						res[key]["validHtml"] = _bone.validHtml
					if( isinstance( _bone, bones.textBone ) ) or ( isinstance( _bone, bones.stringBone ) ):
						res[key]["languages"] = _bone.languages 
		return( res )
	
	def collectSkelData( self, skel ):
		"""
			Prepares values of one :class:`server.db.skeleton.Skeleton` or a list of skeletons for output.

			:param skel: Skeleton which structure will be processed.
			:type skel: server.db.skeleton.Skeleton

			:returns: A dictionary or list of dictionaries.
			:rtype: dict
		"""
		if isinstance( skel, list ):
			return( [ self.collectSkelData(x) for x in skel ] )
		res = {}
		for key,_bone in skel.items():
			if isinstance( _bone, selectOneBone ):
				if _bone.value in _bone.values.keys():
					res[ key ] = Render.KeyValueWrapper( _bone.value, _bone.values[ _bone.value ] )
				else:
					res[ key ] = _bone.value
			elif isinstance( _bone, selectMultiBone ):
				res[ key ] = [ (Render.KeyValueWrapper( val, _bone.values[ val ] ) if val in _bone.values.keys() else val)  for val in _bone.value ]
			elif isinstance(_bone, relationalBone):
				if isinstance(_bone.value, list):
					tmpList = []
					for k in _bone.value:
						if _bone.using is None:
							tmpList.append(self.collectSkelData(k["dest"]))
						else:
							tmpList.append({"dest": self.collectSkelData(k["dest"]),
				                                "rel": self.collectSkelData(k["rel"]) if k["rel"] else None})
					res[key] = tmpList
				elif isinstance(_bone.value, dict):
					if _bone.using is None:
						res[key] = self.collectSkelData(_bone.value["dest"])
					else:
						res[key] = {"dest": self.collectSkelData(_bone.value["dest"]),
						            "rel": self.collectSkelData(_bone.value["rel"]) if _bone.value["rel"] else None}
			elif( isinstance( _bone, bones.baseBone ) ):
				res[ key ] = _bone.value
			if key in res.keys() and isinstance( res[key], list ):
				res[key] = ListWrapper( res[key] )
		return( res )

	def add(self, skel, tpl=None, *args, **kwargs):
		"""
			Renders a page for adding an entry.

			The template must construct the HTML-form on itself; the required information
			are passed via skel.structure, skel.value and skel.errors.

			A jinja2-macro, which builds such kind of forms, is shipped with the server.

			Any data in **kwargs is passed unmodified to the template.

			:param skel: Skeleton of the entry which should be created.
			:type skel: server.db.skeleton.Skeleton

			:param tpl: Name of a different template, which should be used instead of the default one.
			:type tpl: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl and "addTemplate" in dir( self.parent ):
			tpl = self.parent.addTemplate

		tpl = tpl or self.addTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		skeybone = bones.baseBone( descr="SecurityKey",  readOnly=True, visible=False )
		skeybone.value = securitykey.create()
		skel["skey"] = skeybone
		if "nomissing" in request.current.get().kwargs.keys() and request.current.get().kwargs["nomissing"]=="1":
			if isinstance(skel, Skeleton):
				super( Skeleton, skel ).__setattr__( "errors", {} )
			elif isinstance(skel, RelSkel):
				super( RelSkel, skel ).__setattr__( "errors", {} )
		return template.render( skel={"structure":self.renderSkelStructure(skel),
		                                "errors":skel.errors,
		                                "value":self.collectSkelData(skel) }, **kwargs )

	def edit(self, skel, tpl=None, **kwargs):
		"""
			Renders a page for modifying an entry.

			The template must construct the HTML-form on itself; the required information
			are passed via skel.structure, skel.value and skel.errors.

			A jinja2-macro, which builds such kind of forms, is shipped with the server.

			Any data in **kwargs is passed unmodified to the template.

			:param skel: Skeleton of the entry which should be modified.
			:type skel: server.db.skeleton.Skeleton

			:param tpl: Name of a different template, which should be used instead of the default one.
			:type tpl: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl and "editTemplate" in dir( self.parent ):
			tpl = self.parent.editTemplate

		tpl = tpl or self.editTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		skeybone = bones.baseBone( descr="SecurityKey",  readOnly=True, visible=False )
		skeybone.value = securitykey.create()
		skel["skey"]  = skeybone
		if "nomissing" in request.current.get().kwargs.keys() and request.current.get().kwargs["nomissing"]=="1":
			if isinstance(skel, Skeleton):
				super( Skeleton, skel ).__setattr__( "errors", {} )
			elif isinstance(skel, RelSkel):
				super( RelSkel, skel ).__setattr__( "errors", {} )
		return template.render( skel={"structure": self.renderSkelStructure(skel),
		                                "errors": skel.errors,
		                                "value": self.collectSkelData(skel) }, **kwargs )

	def addItemSuccess (self, skel, *args, **kwargs ):
		"""
			Renders a page, informing that the entry has been successfully created.

			:param skel: Skeleton which contains the data of the new entity
			:type skel: server.db.skeleton.Skeleton

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		tpl = self.addSuccessTemplate

		if "addSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.addSuccessTemplate

		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		res = self.collectSkelData( skel )

		return( template.render( { "skel":res }, **kwargs ) )

	def editItemSuccess (self, skel, *args, **kwargs ):
		"""
			Renders a page, informing that the entry has been successfully modified.

			:param skel: Skeleton which contains the data of the modified entity
			:type skel: server.db.skeleton.Skeleton

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		tpl = self.editSuccessTemplate

		if "editSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.editSuccessTemplate

		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		res = self.collectSkelData( skel )

		return( template.render( skel=res, **kwargs ) )
	
	def deleteSuccess (self, *args, **kwargs ):
		"""
			Renders a page, informing that the entry has been successfully deleted.

			The provided parameters depend on the application calling this:
			List and Hierarchy pass the id of the deleted entry, while Tree passes
			the rootNode and path.

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		tpl = self.deleteSuccessTemplate

		if "deleteSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.deleteSuccessTemplate

		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )

		return( template.render( **kwargs ) )
	
	def list( self, skellist, tpl=None, **kwargs ):
		"""
			Renders a list of entries.

			Any data in **kwargs is passed unmodified to the template.

			:param skellist: List of Skeletons with entries to display.
			:type skellist: server.db.skeleton.SkelList

			:param tpl: Name of a different template, which should be used instead of the default one.
			:param: tpl: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl and "listTemplate" in dir( self.parent ):
			tpl = self.parent.listTemplate
		tpl = tpl or self.listTemplate
		try:
			fn = self.getTemplateFileName( tpl )
		except errors.HTTPException as e: #Not found - try default fallbacks FIXME: !!!
			tpl = "list"
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		for x in range(0, len( skellist ) ):
			skellist.append( self.collectSkelData( skellist.pop(0) ) )
		return( template.render( skellist=SkelListWrapper(skellist), **kwargs ) )
	
	def listRootNodes(self, repos, tpl=None, **kwargs ):
		"""
			Renders a list of available repositories.

			:param repos: List of repositories (dict with "key"=>Repo-Key and "name"=>Repo-Name)
			:type repos: list

			:param tpl: Name of a different template, which should be used instead of the default one.
			:param: tpl: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if "listRepositoriesTemplate" in dir( self.parent ):
			tpl = tpl or self.parent.listTemplate
		if not tpl:
			tpl = self.listRepositoriesTemplate
		try:
			fn = self.getTemplateFileName( tpl )
		except errors.HTTPException as e: #Not found - try default fallbacks FIXME: !!!
			tpl = "list"
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( repos=repos, **kwargs ) )
	
	def view( self, skel, tpl=None, **kwargs ):
		"""
			Renders a single entry.

			Any data in **kwargs is passed unmodified to the template.

			:param skel: Skeleton to be displayed.
			:type skellist: server.db.skeleton.Skeleton

			:param tpl: Name of a different template, which should be used instead of the default one.
			:param: tpl: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl and "viewTemplate" in dir( self.parent ):
			tpl = self.parent.viewTemplate

		tpl = tpl or self.viewTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )

		if isinstance( skel, Skeleton ):
			res = self.collectSkelData( skel )
		else:
			res = skel

		return( template.render( skel=res, **kwargs ) )
	
## Extended functionality for the Tree-Application ##
	def listRootNodeContents( self, subdirs, entries, tpl=None, **kwargs):
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

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if "listRootNodeContentsTemplate" in dir( self.parent ):
			tpl = tpl or self.parent.listRootNodeContentsTemplate
		else:
			tpl = tpl or self.listRootNodeContentsTemplate
		template= self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( subdirs=subdirs, entries=[self.collectSkelData( x ) for x in entries], **kwargs) )

	def addDirSuccess(self, rootNode,  path, dirname, *args, **kwargs ):
		"""
			Renders a page, informing that the directory has been successfully created.

			:param rootNode: RootNode-key in which the directory has been created
			:type rootNode: str

			:param path: Path in which the directory has been created
			:type path: str

			:param dirname: Name of the newly created directory
			:type dirname: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""

		tpl = self.addDirSuccessTemplate
		if "addDirSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.addDirSuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( rootNode=rootNode,  path=path, dirname=dirname ) )

	def renameSuccess(self, rootNode, path, src, dest, *args, **kwargs ):
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

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		tpl = self.renameSuccessTemplate
		if "renameSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.renameSuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( rootNode=rootNode,  path=path, src=src, dest=dest ) )

	def copySuccess(self, srcrepo, srcpath, name, destrepo, destpath, type, deleteold, *args, **kwargs ):
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
			:type type: string

			:param deleteold: "0": Copy, "1": Move
			:type deleteold: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		tpl = self.copySuccessTemplate
		if "copySuccessTemplate" in dir( self.parent ):
			tpl = self.parent.copySuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( srcrepo=srcrepo, srcpath=srcpath, name=name, destrepo=destrepo, destpath=destpath, type=type, deleteold=deleteold ) )


	def reparentSuccess(self, obj, tpl=None, **kwargs ):
		"""
			Renders a page informing that the item was successfully moved.
			
			:param obj: ndb.Expando instance of the item that was moved.
			:type obj: ndb.Expando

			:param tpl: Name of a different template, which should be used instead of the default one
			:type tpl: str
		"""
		if not tpl:
			if "reparentSuccessTemplate" in dir( self.parent ):
				tpl = self.parent.reparentSuccessTemplate
			else:
				tpl = self.reparentSuccessTemplate

		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return template.render( skel=skel, repoObj=obj, **kwargs )

	def setIndexSuccess(self, obj, tpl=None, *args, **kwargs ):
		"""
			Renders a page informing that the items sortindex was successfully changed.

			:param obj: ndb.Expando instance of the item that was changed
			:type obj: ndb.Expando

			:param tpl: Name of a different template, which should be used instead of the default one
			:type tpl: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl:
			if "setIndexSuccessTemplate" in dir( self.parent ):
				tpl = self.parent.setIndexSuccessTemplate
			else:
				tpl = self.setIndexSuccessTemplate

		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return template.render( skel=obj, repoObj=obj, **kwargs )

	def cloneSuccess(self, tpl=None, *args, **kwargs ):
		"""
			Renders a page informing that the items sortindex was successfully changed.

			:param obj: ndb.Expando instance of the item that was changed
			:type obj: ndb.Expando

			:param tpl: Name of a different template, which should be used instead of the default one
			:type tpl: str

			:return: Returns the emitted HTML response.
			:rtype: str
		"""
		if not tpl:
			if "cloneSuccessTemplate" in dir( self.parent ):
				tpl = self.parent.cloneSuccessTemplate
			else:
				tpl = self.cloneSuccessTemplate

		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return template.render( **kwargs )

	def renderEmail(self, skel, tpl, dests ):
		"""
			Renders an email.

			:param skel: Skeleton or dict which data to supply to the template.
			:type skel: server.db.skeleton.Skeleton | dict

			:param tpl: Name of the email-template to use. If this string is longer than 100 characters,
			this string is interpreted as the template contents instead of its filename.
			:type tpl: str

			:param dests: Destination recipients.
			:type dests: list | str

			:return: Returns a tuple consisting of email header and body.
			:rtype: str, str
		"""
		headers = {}
		user = utils.getCurrentUser()
		if isinstance(skel, Skeleton) or isinstance(skel, RelSkel):
			res = self.collectSkelData( skel )
		elif isinstance(skel, list) and all([(isinstance(x, Skeleton) or isinstance(x,RelSkel)) for x in skel]):
			res = [ self.collectSkelData( x ) for x in skel ]
		else:
			res = skel
		if len(tpl)<101:
			try:
				template = self.getEnv().from_string(  codecs.open( "emails/"+tpl+".email", "r", "utf-8" ).read() ) 
			except:
				template = self.getEnv().get_template( tpl+".email" )
		else:
			template = self.getEnv().from_string( tpl )
		data = template.render( skel=res, dests=dests, user=user )
		body = False
		lineCount=0
		for line in data.splitlines():
			if lineCount>3 and body is False:
				body = "\n\n"
			if body != False:
				body += line+"\n"
			else:
				if line.lower().startswith("from:"):
					headers["from"]=line[ len("from:"):]
				elif line.lower().startswith("subject:"):
					headers["subject"]=line[ len("subject:"): ]
				elif line.lower().startswith("references:"):
					headers["references"]=line[ len("references:"):]
				else:
					body="\n\n"
					body += line
			lineCount += 1
		return( headers, body )

	def getEnv(self):
		"""
		Constucts the Jinja2 environment.

		If an application specifies an jinja2Env function, this function
		can alter the environment before its used to parse any template.

		:returns: Extended Jinja2 environment.
		:rtype jinja2.Environment
		"""
		def mkLambda(func, s):
			return lambda *args, **kwargs: func(s, *args, **kwargs)
		if not "env" in dir(self):
			loaders = self.getLoaders()
			self.env = Environment(loader=loaders, extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])

			# Translation remains global
			self.env.globals["_"] = _
			self.env.filters["tr"] = _

			# Import functions.
			for name, func in jinjaUtils.getGlobals().items():
				logging.debug("Adding global '%s'" % name)
				self.env.globals[name] = mkLambda(func, self)

			# Import filters.
			for name, func in jinjaUtils.getFilters().items():
				logging.debug("Adding filter '%s'" % name)
				self.env.filters[name] = mkLambda(func, self)

			# Import extensions.
			for ext in jinjaUtils.getExtensions():
				logging.debug("Adding extension '%s'" % ext)
				self.env.add_extension(ext)

			# Import module-specific environment, if available.
			if "jinjaEnv" in dir(self.parent):
				self.env = self.parent.jinjaEnv(self.env)

		return self.env

