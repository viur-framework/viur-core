# -*- coding: utf-8 -*-
from server import conf, bones, utils, request, session, conf, errors, securitykey, prototypes
from server.skeleton import Skeleton, RelSkel
from server.bones import *

from collections import OrderedDict
from jinja2 import Environment, FileSystemLoader, ChoiceLoader
from urllib import urlencode, quote_plus
from hashlib import sha512

from google.appengine.ext import db
from google.appengine.api import memcache, users
from google.appengine.api.images import get_serving_url

from datetime import datetime
import re, os, logging, codecs, json, pprint

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
						res[key]["values"] = dict( [(k,_(v)) for (k,v) in _bone.values.items() ] )
						res[key]["sortBy"] = _bone.sortBy
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


	# JINJA2 ENV ------------------------------------------------------------------------------------------------------
	# ---------- JINJA2 ENV -------------------------------------------------------------------------------------------
	# --------------------- JINJA2 ENV --------------------------------------------------------------------------------

	def getEnv(self):
		"""
		Constucts the Jinja2 environment.

		If an application specifies an jinja2Env function, this function
		can alter the environment before its used to parse any template.

		:returns: Extended Jinja2 environment.
		:rtype jinja2.Environment
		"""

		if not "env" in dir( self ):
			loaders = self.getLoaders()
			self.env = Environment(loader=loaders, extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])

			# Globals (functions)
			functions = [
				"execRequest",
				"getConf",
				"getCurrentUser",
				"getEntry",
				"getHostURL",
				"getLanguage",
				"getList",
				"getResizedURL",
				"getSecurityKey",
				"getSession",
				"getSkel",
				"logging",
				"moduleName",
				"modulePath",
				"now",
				"parseJSON",
				"pprint",
				"regexMatch",
				"regexReplace",
				"regexSearch",
				"requestParams",
				"setSession",
				"updateURL",
			]

			for fn in functions:
				name = "j2glob" + fn[0].upper() + fn[1:]
				if name in dir(self) and callable(getattr(self, name)):
					self.env.globals[fn] = getattr(self, name)
				else:
					logging.warning("Function '%s' defined but not implemented" % name)

			self.env.globals["_"] = _

			# Filters
			filters = [
				"fileSize",
				"shortKey",
				"className",
				"urlencode",
			]

			for flt in filters:
				name = "j2flt" + flt[0].upper() + flt[1:]
				if name in dir(self) and callable(getattr(self, name)):
					self.env.filters[flt] = getattr(self, name)

			self.env.filters["tr"] = _

			if "jinjaEnv" in dir(self.parent):
				self.env = self.parent.jinjaEnv(self.env)

		return self.env

	def j2globExecRequest( self, path, *args, **kwargs ):
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

		if conf["viur.disableCache"] or request.current.get().disableCache: #Caching disabled by config
			cachetime = 0

		if cachetime:
			#Calculate the cache key that entry would be stored under
			tmpList = ["%s:%s" % (unicode(k), unicode(v)) for k,v in kwargs.items()]
			tmpList.sort()
			tmpList.extend(list(args))
			tmpList.append(path)

			if conf[ "viur.cacheEnvironmentKey" ]:
				tmpList.append( conf[ "viur.cacheEnvironmentKey" ]() )

			try:
				appVersion = request.current.get().request.environ["CURRENT_VERSION_ID"].split('.')[0]
			except:
				appVersion = ""
				logging.error("Could not determine the current application id! Caching might produce unexpected results!")

			tmpList.append( appVersion )
			mysha512 = sha512()
			mysha512.update( unicode(tmpList).encode("UTF8") )
			cacheKey = "jinja2_cache_%s" % mysha512.hexdigest()
			res = memcache.get( cacheKey )

			if res:
				return res

		currentRequest = request.current.get()
		tmp_params = currentRequest.kwargs.copy()
		currentRequest.kwargs = {"__args": args, "__outer": tmp_params}
		currentRequest.kwargs.update( kwargs )
		lastRequestState = currentRequest.internalRequest
		currentRequest.internalRequest = True
		caller = conf["viur.mainApp"]
		pathlist = path.split("/")

		for currpath in pathlist:
			if currpath in dir( caller ):
				caller = getattr( caller,currpath )
			elif "index" in dir( caller ) and  hasattr( getattr( caller, "index" ), '__call__'):
				caller = getattr( caller, "index" )
			else:
				currentRequest.kwargs = tmp_params # Reset RequestParams
				currentRequest.internalRequest = lastRequestState
				return( u"Path not found %s (failed Part was %s)" % ( path, currpath ) )

		if (not hasattr(caller, '__call__')
			or ((not "exposed" in dir( caller )
				 	or not caller.exposed))
			and (not "internalExposed" in dir( caller )
					or not caller.internalExposed)):
			currentRequest.kwargs = tmp_params # Reset RequestParams
			currentRequest.internalRequest = lastRequestState
			return( u"%s not callable or not exposed" % str(caller) )

		try:
			resstr = caller( *args, **kwargs )
		except Exception as e:
			logging.error("Caught execption in execRequest while calling %s" % path)
			logging.exception(e)
			raise

		currentRequest.kwargs = tmp_params
		currentRequest.internalRequest = lastRequestState

		if cachetime:
			memcache.set(cacheKey, resstr, cachetime)

		return resstr

	def j2globGetConf(self):
		"""
		Jinja2 global: Allows for accessing the ViUR application config.

		The returned dict only contains config entries which are listed in the "viur.config.whitelist"
		configuration key. Everything else will not be made available.

		:return: All whitelisted ViUR configuration parameters.
		:rtype: dict
		"""
		retconf = {}

		for ele in conf:
			if ele in conf["viur.config.whitelist"]:
				retconf.update({ele: conf[ele]})

		return retconf

	def j2globGetCurrentUser( self ):
		"""
		Jinja2 global: Returns the current user from the session, or None if not logged in.

		:return: A dict containing user data. Returns None if no user data is available.
		:rtype: dict
		"""
		return utils.getCurrentUser()

	def j2globGetEntry(self, module, key=None, skel="viewSkel"):
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
				#We fetching the entry from a singleton - No key needed
				key = str(db.Key.from_path(skel.kindName, obj.getKey()))
			elif not key:
				logging.info("getEntry called without a valid key")
				return False

			if not isinstance(skel,  Skeleton):
				return False

			if "listFilter" in dir(obj):
				qry = skel.all().mergeExternalFilter({"key": str(key)})
				qry = obj.listFilter(qry)
				if not qry:
					logging.info("listFilter permits getting entry, returning None")
					return None

				skel = qry.getSkel()
				if not skel:
					return None

			else: # No Access-Test for this module
				if not skel.fromDB(key):
					return None

			return self.collectSkelData(skel)

		return False

	def j2globGetHostURL(self, forceSSL = False, *args, **kwargs):
		"""
		Jinja2 global: Retrieve hostname with protocol.

		:returns: Returns the hostname, including the currently used protocol, e.g: http://www.example.com
		:rtype: str
		"""
		url = request.current.get().request.url
		url = url[ :url.find("/", url.find("://")+5) ]

		if forceSSL and url.startswith("http://"):
			url = "https://" + url[7:]

		return url

	def j2globGetLanguage(self, resolveAlias=False):
		"""
		Jinja2 global: Returns the language used for this request.

		:param resolveAlias: If True, the function tries to resolve the current language
		using conf["viur.languageAliasMap"].
		:type resolveAlias: bool
		"""
		lang = request.current.get().language
		if resolveAlias and lang in conf["viur.languageAliasMap"].keys():
			lang = conf["viur.languageAliasMap"][ lang ]

		return lang

	def j2globGetList(self, module, skel="viewSkel", _noEmptyFilter=False, *args, **kwargs):
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

		caller = getattr( conf["viur.mainApp"], module)
		if not skel in dir( caller ):
			logging.error("Jinja2-Render cannot fetch a list with an unknown skeleton %s!" % skel)
			return False

		if _noEmptyFilter: #Test if any value of kwargs is an empty list
			if any( [isinstance(x,list) and not len(x) for x in kwargs.values()] ):
				return []

		query = getattr(caller, skel)().all()
		query.mergeExternalFilter(kwargs)

		if "listFilter" in dir(caller):
			query = caller.listFilter(query)

		if query is None:
			return None

		mylist = query.fetch()

		for x in range(0, len(mylist)):
			mylist.append(self.collectSkelData(mylist.pop(0)))

		return SkelListWrapper(mylist)

	def j2globGetResizedURL(self, dlkey):
		"""
		Jinja2 global: Returns the serving URL for a download key.
		"""
		return get_serving_url(dlkey)

	def j2globGetSecurityKey(self, **kwargs):
		"""
		Jinja2 global: Creates a new ViUR security key.
		"""
		return securitykey.create(kwargs)

	def j2globGetSession(self):
		"""
		Jinja2 global: Allows templates to store variables server-side inside the session.

		Note: This is done in a separated part of the session for security reasons.

		:returns: A dictionary of session variables.
		:rtype: dict
		"""
		if not session.current.get("JinjaSpace"):
			session.current["JinjaSpace"] = {}

		return session.current.get("JinjaSpace")

	def j2globGetSkel(self, module, skel = "viewSkel", subSkel = None):
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

			if isinstance(skel, Skeleton) or isinstance(skel, RelSkel):
				if subSkel is not None:
					try:
						skel = skel.subSkel(subSkel)
					except Exception as e:
						logging.exception(e)
						return False

				return self.renderSkelStructure(skel)

		return False

	def j2globLogging(self, msg, kind = "info"):
		"""
		Jinja2 global: Write log-level entry.
		The function shall be used for debug and tracing purposes.

		:param msg: Message to be delivered into logging.
		:type msg: str

		:param kind: Logging kind. This can either be "info" (default), "debug", "warning", "error" or "critical".
		:type kind: str
		"""

		kind = kind.lower()

		if kind == "critical":
			logging.critical(msg)
		elif kind == "error":
			logging.error(msg)
		elif kind == "warning":
			logging.warning(msg)
		elif kind == "debug":
			logging.debug(msg)
		else:
			logging.info(msg)

	def j2globModuleName(self):
		"""
		Jinja2 global: Retrieve name of current module where this renderer is used within.

		:return: Returns the name of the current module, or empty string if there is no module set.
		"""
		if self.parent and "moduleName" in dir(self.parent):
			return self.parent.moduleName

		return ""

	def j2globModulePath(self):
		"""
		Jinja2 global: Retrieve path of current module the renderer is used within.

		:return: Returns the path of the current module, or empty string if there is no module set.
		"""
		if self.parent and "modulePath" in dir(self.parent):
			return self.parent.modulePath

		return ""

	def j2globNow(self):
		"""
		Jinja2 global: Returns the current date and time.

		:return: The current date & time.
		:rtype: datetime
		"""
		return datetime.now()

	def j2globParseJSON(self, s):
		"""
		Jinja2 global: Parse a JSON-string into a dict.

		:param s: The string to be parsed.
		:type s: str

		:return: The parsed dict object.
		:rtype: dict
		"""
		return json.loads(s)

	def j2globPprint(self,obj):
		"""
		Jinja2 global: Provides a pprint function that renders into HTML.
		The function shall be used for debug purposes.

		:param obj: Object to be pprinted.
		:return: HTML-enabled pprint output.
		"""
		return pprint.pformat(obj).replace("\n", "<br>").replace(" ", "&nbsp;")

	def j2globRegexMatch(self, pattern, string, flags = 0):
		"""
		Jinja2 global: Match a string for regular expression pattern.
		This function internally runs re.match().

		:param s: String where to be searched in.
		:type s: str

		:param pattern: Regular expression pattern to be matched.
		:type pattern: str

		:param flags: Flags to be passed to re.search().
		:type flags: int

		:return: A matching object on success, else None.
		:rtype: ``re.MatchObject``
		"""
		return re.match(pattern,string)

	def j2globRegexReplace(self, s, pattern, replace):
		"""
		Jinja2 global: Replace string by regular expression pattern.

		:param s: String to be replaced.
		:type s: str

		:param pattern: Regular expression pattern to be matched.
		:type pattern: str

		:param replace: Replacement string to be inserted for every matching pattern.
		:type replace: str

		:return: The string with the replaced matches.
		:rtype: str
		"""
		return re.sub(pattern, replace, s)

	def j2globRegexSearch(self, s, pattern, flags = 0):
		"""
		Jinja2 global: Search a string for regular expression pattern.
		This function internally runs re.search().

		:param s: String where to be searched in.
		:type s: str

		:param pattern: Regular expression pattern to be matched.
		:type pattern: str

		:param flags: Flags to be passed to re.search().
		:type flags: int

		:return: A matching object on success, else None.
		:rtype: ``re.MatchObject``
		"""
		return re.search(pattern, s, flags)

	def j2globRequestParams(self):
		"""
		Jinja2 global: Allows for accessing the request-parameters from the template.

		These returned values are escaped, as users tend to use these in an unsafe manner.

		:returns: Dict of parameter and values.
		:rtype: dict
		"""
		res = {}
		for k, v in request.current.get().kwargs.items():
			res[ utils.escapeString( k ) ] = utils.escapeString( v )
		return res

	def j2globSetSession(self,name,value):
		"""
		Jinja2 global: Allows templates to store variables on server-side inside the session.

		Note: This is done in a separated part of the session for security reasons.

		:param name: Name of the key
		:type name: str

		:param value: Value to store with name.
		:type value: any
		"""
		sessionData = self.getSession()
		sessionData[name]=value
		session.current["JinjaSpace"]= sessionData
		session.current.markChanged()

	def j2globUpdateURL( self, **kwargs ):
		"""
		Jinja2 global: Constructs a new URL based on the current requests url.

		Given parameters are replaced if they exists in the current requests url, otherwise there appended.

		:returns: Returns a well-formed URL.
		:rtype: str
		"""
		tmpparams = {}
		tmpparams.update(request.current.get().kwargs)

		for key in list(tmpparams.keys()):
			if key[0]=="_":
				del tmpparams[ key ]
			elif isinstance( tmpparams[ key ], unicode ):
				tmpparams[ key ] = tmpparams[ key ].encode("UTF-8", "ignore")

		for key, value in list(kwargs.items()):
			if value is None:
				if value in tmpparams.keys():
					del tmpparams[ key ]
			else:
				tmpparams[key] = value

		return "?" + urlencode(tmpparams).replace("&", "&amp;")

	def j2fltFileSize(self, value, binary=False):
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

	def j2fltUrlencode(self, val ):
		"""
		Jinja2 filter: Make a string URL-safe.

		:param val: String to be quoted.
		:type val: str

		:returns: Quoted string.
		:rtype: str
		"""

		#quote_plus fails if val is None
		if not val:
			return ""

		if isinstance(val, unicode):
			val = val.encode("UTF-8")

		return quote_plus(val)

	def j2fltClassName(self, s):
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

	def j2fltShortKey(self, val):
		"""
		Jinja2 filter: Make a shortkey from an entity-key.

		:param val: Entity-key as string.
		:type val: str

		:returns: Shortkey on success, None on error.
		:rtype: str
		"""

		try:
			k = db.Key(encoded = unicode(val))
			return k.id_or_name()
		except:
			return None

