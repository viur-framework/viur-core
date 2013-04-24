# -*- coding: utf-8 -*-
import time
from string import Template
from server import bones, utils, request, session, conf, errors
from server.skeleton import Skeleton
from server.bones import *
from server.applications.singleton import Singleton
import string
import codecs
from jinja2 import Environment, FileSystemLoader, ChoiceLoader
import datetime
from math import ceil
import os
from collections import OrderedDict
import threading
from server import conf
from server.skeleton import Skeleton
import logging
from google.appengine.api import memcache, users
from google.appengine.api.images import get_serving_url
from urllib import urlencode, quote_plus
from google.appengine.ext import db

class Render( object ):
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
	
	class KeyValueWrapper:
		"""
			This holds one Key-Value pair for
			selectOne/selectMulti Bones.
			It allows to directly treat the key as string,
			but still makes the translated description of that
			key avaiable.
		"""
		def __init__( self, key, descr ):
			self.key = key
			self.descr = _( descr )

		def __str__( self ):
			return( unicode( self.key ) )
		
		def __repr__( self ):
			return( unicode( self.key ) )
		
		def __eq__( self, other ):
			return( self.key == other )
			
		def __trunc__( self ):
			return( self.key.__trunc__() )

	def __init__(self, parent=None, *args, **kwargs ):
		super( Render, self ).__init__(*args, **kwargs)
		self.parent = parent

	
	def getTemplateFileName( self, template, ignoreStyle=False ):
		"""
			Returns the filename of the template.
			This decides in which language and which style a given template is rendered.
			If getLoaders if overriden, this method should be also.
			@param template: Name of the template to use
			@type template: string
			@param ignoreStyle: Ignore any maybe given style hints
			@type ignoreStyle: bool
			@returns: Filename of the template
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
		lang = session.current.getLanguage()
		fnames = [ template+stylePostfix+".html", template+".html" ]
		if lang:
			fnames = [ 	os.path.join(  lang, template+stylePostfix+".html"),
						template+stylePostfix+".html", 
						os.path.join(  lang, template+".html"), 
						template+".html" ]
		for fn in fnames: #Check the templatefolder of the application
			if os.path.isfile( os.path.join( os.getcwd(), htmlpath, fn ) ):
				return( fn )
		for fn in fnames: #Check the fallback
			if os.path.isfile( os.path.join( os.getcwd(), "server", "template", fn ) ):
				return( fn )
		raise errors.NotFound( "Template %s not found." % template )
	
	def getLoaders(self):
		"""
			Return the List of Jinja2-Loaders which should be used.
			May be overriden to provide an alternative loader
			(eg. fetch templates from the datastore).
		"""
		if "htmlpath" in dir( self ):
			htmlpath = self.htmlpath
		else:
			htmlpath = "html/"
		return( ChoiceLoader( [FileSystemLoader( htmlpath ), FileSystemLoader( "server/template/" )] ) )
	
	def getEnv( self ):
		"""
			Constucts the Jinja2 environment.
			If an application specifies an jinja2Env function, this function 
			can alter the enviroment before its used to parse any template.
			@returns: Jinja2 Enviroment
		"""
		if "htmlpath" in dir( self ):
			htmlpath = self.htmlpath
		else:
			htmlpath = "html/"
		if not "env" in dir( self ):
			loaders = self.getLoaders()
			self.env = Environment( loader=loaders, extensions=['jinja2.ext.do', 'jinja2.ext.loopcontrols'], line_statement_prefix="##" )
			self.env.globals["requestParams"] = self.getRequestParams
			self.env.globals["getSession"] = self.getSession
			self.env.globals["setSession"] = self.setSession
			self.env.globals["getSkel"] = self.getSkel
			self.env.globals["getEntry"] = self.getEntry
			self.env.globals["getList"] = self.fetchList
			self.env.globals["getSecurityKey"] = utils.createSecurityKey
			self.env.globals["getCurrentUser"] = self.getCurrentUser
			self.env.globals["getResizedURL"] = get_serving_url
			self.env.globals["updateURL"] = self.updateURL
			self.env.globals["execRequest"] = self.execRequest
			self.env.globals["getHostUrl" ] = self.getHostUrl
			self.env.globals["getLanguage" ] = lambda *args, **kwargs: session.current.getLanguage()
			self.env.globals["modulName"] = lambda *args, **kwargs: self.parent.modulName
			self.env.globals["modulPath"] = lambda *args, **kwargs: self.parent.modulPath
			self.env.globals["_"] = _
			self.env.filters["tr"] = _
			self.env.filters["urlencode"] = self.quotePlus
			self.env.filters["shortKey"] = self.shortKey
			if "jinjaEnv" in dir( self.parent ):
				self.env = self.parent.jinjaEnv( self.env )
		return( self.env )

	def execRequest( self, path, *args, **kwargs ):
		"""
			Starts an internal Request.
			This allows a template to embed the result of another
			request inside the current response.
			All optional parameters are passed to the requested ressource.
			@param path: Local part of the url. eg. user/list. Must not start with an /. Must not include an protocol or hostname.
			@type path: String
			@returns: Whatever the requested ressource returns. This is *not* limited to strings!
		"""
		if "cachetime" in kwargs:
			cachetime = kwargs["cachetime"]
			del( kwargs["cachetime"] )
		else:
			cachetime=0
		if cachetime:
			cacheKey = str(path)+str(args)+str(kwargs)
			res = memcache.get( cacheKey )
			if res:
				return( res )
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
		if (not hasattr(caller, '__call__') or ((not "exposed" in dir( caller ) or not caller.exposed)) and (not "internalExposed" in dir( caller ) or not caller.internalExposed)):
			currentRequest.kwargs = tmp_params # Reset RequestParams
			currentRequest.internalRequest = lastRequestState
			return( u"%s not callable or not exposed" % str(caller) )
		resstr = caller( *args, **kwargs )
		currentRequest.kwargs = tmp_params
		currentRequest.internalRequest = lastRequestState
		if cachetime:
			memcache.set( cacheKey, resstr, cachetime )
		return( resstr )
	
	def getCurrentUser( self ):
		return( utils.getCurrentUser() )
	
	def getHostUrl(self, *args,  **kwargs):
		"""
			Returns the hostname, including the currently used Protocol.
			Eg: http://www.example.com
			@returns: String
		"""
		url = request.current.get().request.url
		url = url[ :url.find("/", url.find("://")+5) ]
		return( url )

	def updateURL( self, **kwargs ):
		"""
			Constructs a new URL based on the current requests url.
			Given parameters are replaced if they exists in the current requests url,
			otherwise there appended.
			@returns: String
		"""
		tmpparams = {}
		tmpparams.update( request.current.get().kwargs )
		for key in list(tmpparams.keys()):
			if key[0]=="_":
				del tmpparams[ key ]
			elif isinstance( tmpparams[ key ], str ):
				tmpparams[ key ] = tmpparams[ key ].encode("UTF-8", "ignore")
		for key, value in list(kwargs.items()):
			if value==None:
				if value in tmpparams.keys():
					del tmpparams[ key ]
			else:
				tmpparams[key] = value
		return "?"+ urlencode( tmpparams ).replace("&","&amp;" )
		
	def getRequestParams(self):
		"""
			Allows accessing the request-parameters from the template
			Warning: They where not santinized!
			@returns: Dict
		"""
		return request.current.get().kwargs
	
	def getSession(self):
		"""
			Allows templates to store variables server-side inside the session.
			Note: This is seperate part of the session for security-reasons.
			@returns: Dict
		"""
		if not session.current.get("JinjaSpace"):
			session.current["JinjaSpace"] = {}
		return session.current.get("JinjaSpace")
	
	def setSession(self,name,value):
		"""
			Allows templates to store variables server-side inside the session.
			Note: This is seperate part of the session for security-reasons.
			@param name: Name of the key to store the value under
			@type name: String
			@param value: Value to store
		"""
		sessionData = self.getSession()
		sessionData[name]=value
		session.current["JinjaSpace"]= sessionData
		session.current.markChanged()
	
	def getEntry(self,  modul, id=None, skel="viewSkel"  ):
		"""
			Fetch an entry from a given modul, and return
			the data as dict (prepared for direct use in the output).
			Its possible to specify a different data-model as the one
			normally used for rendering (eg. an editSkel)
			@param modul: Modulname, from which the data should be fetched
			@type modul: String
			@param id: Enity-Key in urlsafe format
			@type id: String
			@param skel: Optional different datamodell
			@type skel: String
			@returns: Dict
		"""
		if not modul in dir ( conf["viur.mainApp"] ):
			return False
		obj = getattr( conf["viur.mainApp"], modul)
		if skel in dir( obj ):
			skel = getattr( obj , skel)()
			if isinstance( obj, Singleton ) and not id:
				#We fetching the entry from a singleton - No id needed
				id = str( db.Key.from_path( skel.kindName, obj.getKey() ) )
			if isinstance( skel,  Skeleton ):
				skel.fromDB( id )
				return( self.collectSkelData( skel ) )
		return False

	def getSkel(self,  modul,  skel="viewSkel"):
		"""
			Returns the structure instead of data of an skeleton.
			@param modul: Modul from which the skeleton should be retrived
			@type modul: String
			@param skel: Name of the skeleton.
			@type skel: String
		
		"""
		if not modul in dir ( conf["viur.mainApp"] ):
			return False
		obj = getattr( conf["viur.mainApp"], modul)
		if skel in dir( obj ):
			skel = getattr( obj , skel)()
			if isinstance( skel,  Skeleton ):
				return( self.renderSkelStructure( skel ) )
		return False

	def fetchList(self, modul, skel="viewSkel",  *args,  **kwargs ):
		"""
			Fetches a list of entries which match the given criteria.
			@param modul: Modul from which the skeleton should be retrived
			@type modul: String
			@param skel: Name to the skeleton to fetch the list from
			@type skel: String
			@returns: List or None
		"""
		if not modul in dir ( conf["viur.mainApp"] ):
			logging.error("Jinja2-Render can't fetch a list from an unknown modul %s!" % modul)
			return( False )
		caller = getattr( conf["viur.mainApp"], modul)
		if not skel in dir( caller ):
			logging.error("Jinja2-Render can't fetch a list with an unknown skeleton %s!" % skel)
			return( False )
		query = getattr(caller, skel )().all()
		query.mergeExternalFilter( kwargs )
		if "listFilter" in dir( caller ):
			query = caller.listFilter( query )
		if query is None:
			return( None )
		mylist = query.fetch()
		for x in range(0, len( mylist ) ):
			mylist.append( self.collectSkelData( mylist.pop(0) ) )
		return( mylist )
	
	def quotePlus(self, val ):
		if isinstance( val, unicode ):
			val = val.encode("UTF-8")
		return( quote_plus( val ) )

	def shortKey( self, val ):
		try:
			k = db.Key( encoded=unicode( val ) )
			return( k.id_or_name() )
		except: 
			return( None )

	def renderSkelStructure(self, skel ):
		"""
			Dumps the Structure of a Skeleton.
			@param skel: Skeleton which structure will be processed
			@type skel: Skeleton
			@returns: Dict
		"""
		res = OrderedDict()
		for key, _bone in skel.items():
			if "__" not in key:
				if( isinstance( _bone, bones.baseBone ) ):
					res[ key ] = {	"descr":  _(_bone.descr ), 
							"type": _bone.type,
							"required":_bone.required,
							"params":_bone.params,
							"visible": _bone.visible
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
						res[key]["multiple"]=_bone.multiple
						res[key]["format"] = _bone.format
					if( isinstance( _bone, bones.selectOneBone ) or isinstance( _bone, bones.selectMultiBone ) ):
						res[key]["values"] = dict( [(k,_(v)) for (k,v) in _bone.values.items() ] )
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
			Prepares Values of one Skeleton for Output.
			@type skel: Skeleton
			@returns: Dict
		"""
		res = {}
		for key in dir( skel ):
			if "__" not in key:
				_bone = getattr( skel, key )
				if( isinstance( _bone, bones.documentBone ) ): #We flip source-html and parsed (cached) html for a more natural use
					res[key] = _bone.cache
				elif isinstance( _bone, selectOneBone ):
					if _bone.value in _bone.values.keys():
						res[ key ] = Render.KeyValueWrapper( _bone.value, _bone.values[ _bone.value ] )
					else:
						res[ key ] = _bone.value
				elif isinstance( _bone, selectMultiBone ):
					res[ key ] = [ (Render.KeyValueWrapper( val, _bone.values[ val ] ) if val in _bone.values.keys() else val)  for val in _bone.value ]
				elif( isinstance( _bone, bones.baseBone ) ):
					res[ key ] = _bone.value
		return( res )

	def add( self, skel, tpl=None,*args,**kwargs ):
		"""
			Renders a page for adding an entry.
			The template must construct the html-form itself; the required informations
			are passed as skel.structure, skel.value and skel.errors.
			An jinja2-macro, wich builds such an form, is shipped with the server.
			@param skel: Skeleton of the entry which should be created
			@type skel: Skeleton
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		tpl = tpl or self.addTemplate
		if "addTemplate" in dir( self.parent ):
			tpl = self.parent.addTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		skeybone = bones.baseBone( descr="SecurityKey",  readOnly=True, visible=False )
		skeybone.value = utils.createSecurityKey()
		skel.skey = skeybone
		if "nomissing" in request.current.get().kwargs.keys() and request.current.get().kwargs["nomissing"]=="1":
			skel.errors = {}
		return( template.render( skel={"structure":self.renderSkelStructure(skel),"errors":skel.errors, "value":self.collectSkelData(skel) } ) )
	
	def edit( self, skel, tpl=None, **kwargs ):
		"""
			Renders a page for modifying an entry.
			The template must construct the html-form itself; the required informations
			are passed as skel.structure, skel.value and skel.errors.
			An jinja2-macro, wich builds such an form, is shipped with the server.
			@param skel: Skeleton of the entry which should be modified
			@type skel: Skeleton
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		tpl = tpl or self.editTemplate
		if "editTemplate" in dir( self.parent ):
			tpl = self.parent.editTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		skeybone = bones.baseBone( descr="SecurityKey",  readOnly=True, visible=False )
		skeybone.value = utils.createSecurityKey()
		skel.skey = skeybone
		if "nomissing" in request.current.get().kwargs.keys() and request.current.get().kwargs["nomissing"]=="1":
			skel.errors = {}
		return( template.render( skel={"structure":self.renderSkelStructure(skel),"errors":skel.errors, "value":self.collectSkelData(skel) },  **kwargs) )
	
	def addItemSuccess (self, id, skel, *args, **kwargs ):
		"""
			Render an page, informing that the entry has been successfully created.
			@param id: Urlsafe key of the new entry
			@type id: String
			@param skel: Skeleton which contains the data of the new entity
			@type skel: Skeleton
		"""
		tpl = self.addSuccessTemplate
		if "addSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.addSuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		res = self.collectSkelData( skel )
		return( template.render( {"id":id, "skel":res} ) )

	def editItemSuccess (self, skel, *args, **kwargs ):
		"""
			Render an page, informing that the entry has been successfully modified.
			@param skel: Skeleton which contains the data of the new entity
			@type skel: Skeleton
		"""
		tpl = self.editSuccessTemplate
		if "editSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.editSuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		res = self.collectSkelData( skel )
		return( template.render( skel=res ) )	
	
	def deleteSuccess (self, *args, **kwargs ):
		"""
			Render an page, informing that the entry has been successfully deleted.
			Parameters depends on the application calling this:
			List and Hierachy pass the id of the deleted Entry, while Tree passes the rootNode and path.
		"""
		tpl = self.deleteSuccessTemplate
		if "deleteSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.deleteSuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( **kwargs ) )	
	
	def list( self, skellist, tpl=None, **kwargs ):
		"""
			Renders a list of entries.
			@param skellist: Skellist-instance which the entries to display
			@type skellist: Skellist
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		if "listTemplate" in dir( self.parent ):
			tpl = tpl or self.parent.listTemplate
		if not tpl:
			tpl = self.listTemplate
		try:
			fn = self.getTemplateFileName( tpl )
		except errors.HTTPException as e: #Not found - try default fallbacks FIXME: !!!
			tpl = "list"
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		for x in range(0, len( skellist ) ):
			skellist.append( self.collectSkelData( skellist.pop(0) ) )
		return( template.render( skellist=skellist, **kwargs ) )
	
	def listRootNodes(self, repos, tpl=None, **kwargs ):
		"""
			Renders a list of available repositories.
			@param repos: List of repositories ( Dictionaries with "key"=>Repo-Key and "name"=>Repo-Name )
			@type repos: List
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
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
			Renders a page to display a single item
			@param skel: Skeleton which contains the data of the entity
			@type skel: Skeleton
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		if "viewTemplate" in dir( self.parent ):
			tpl = tpl or self.parent.viewTemplate
		else:
			tpl = tpl or self.viewTemplate
		template= self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		if isinstance( skel, Skeleton ):
			res = self.collectSkelData( skel )
		else:
			res = skel
		return( template.render( skel=res, **kwargs ) )
	
## Extended functionality for the Tree-Application ##
	def listRootNodeContents( self, subdirs, entries, tpl=None, **kwargs):
		"""
			Renders the contents of a given RootNode.
			This differs from list(), as one level in the tree-application may contains two different Child-Types: Entries and Folders.
			@param subdirs: List of (sub-) Directories on the current level
			@type repos: List
			@param entries: Skellist-instance which the entries of the current level
			@type entries: Skellist
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		if "listRootNodeContentsTemplate" in dir( self.parent ):
			tpl = tpl or self.parent.listRootNodeContentsTemplate
		else:
			tpl = tpl or self.listRootNodeContentsTemplate
		template= self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( subdirs=subdirs, entries=[self.collectSkelData( x ) for x in entries], **kwargs) )

	def addDirSuccess(self, rootNode,  path, dirname, *args, **kwargs ):
		"""
			Render an page, informing that the directory has been successfully created.
			@param rootNode: RootNode-key in which the directory has been created
			@type rootNode: String
			@param path: Path in which the directory has been created
			@type path: String:
			@param dirname: Name of the newly created directory
			@type dirname: string
			@type skel: Skeleton
		"""
		tpl = self.addDirSuccessTemplate
		if "addDirSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.addDirSuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( rootNode=rootNode,  path=path, dirname=dirname ) )

	def renameSuccess(self,  rootNode, path, src, dest, *args, **kwargs ):
		"""
			Render an page, informing that an entry has been successfully renamed.
			@param rootNode: RootNode-key in which the entry has been renamed
			@type rootNode: String
			@param path: Path in which the entry has been renamed
			@type path: String:
			@param src: Old name of the entry
			@type src: string
			@param dest: New name of the entry
			@type dest: string
			@type skel: Skeleton
		"""
		tpl = self.renameSuccessTemplate
		if "renameSuccessTemplate" in dir( self.parent ):
			tpl = self.parent.renameSuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( rootNode=rootNode,  path=path, src=src, dest=dest ) )

	def copySuccess(self, srcrepo, srcpath, name, destrepo, destpath, type, deleteold, *args, **kwargs ):
		"""
			Render an page, informing that an entry has been successfully copied/moved.
			@param srcrepo: RootNode-key from which has been copied/moved
			@type srcrepo: String
			@param srcpath: Path from which the entry has been copied/moved
			@type srcpath: String
			@type name: Name of the entry which has been copied/moved
			@type name: String
			@param destrepo: RootNode-key to which has been copied/moved
			@type destrepo: String
			@param destpath: Path to which the entries has been copied/moved
			@type destpath: String
			@param type: "entry": Copy/Move an entry, everything else: Copy/Move an directory
			@type type: string
			@param deleteold: "0": Copy, "1": Move
			@type deleteold: string
		"""
		tpl = self.copySuccessTemplate
		if "copySuccessTemplate" in dir( self.parent ):
			tpl = self.parent.copySuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( srcrepo=srcrepo, srcpath=srcpath, name=name, destrepo=destrepo, destpath=destpath, type=type, deleteold=deleteold ) )


	def reparentSuccess(self, repoObj, tpl=None, **kwargs ):
		"""
			Renders a page informing that the item was successfully moved.
			@param repoObj: ndb.Expando instance of the item that was moved
			@type repoObj: ndb.Expando
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		if not tpl:
			if "reparentSuccessTemplate" in dir( self.parent ):
				tpl = self.parent.reparentSuccessTemplate
			else:
				tpl = self.reparentSuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( repoObj=repoObj, **kwargs ) )

	def setIndexSuccess(self, dbobj, tpl=None, *args, **kwargs ):
		"""
			Renders a page informing that the items sortindex was successfully changed.
			@param repoObj: ndb.Expando instance of the item that was changed
			@type repoObj: ndb.Expando
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		if not tpl:
			if "setIndexSuccessTemplate" in dir( self.parent ):
				tpl = self.parent.setIndexSuccessTemplate
			else:
				tpl = self.setIndexSuccessTemplate
		template = self.getEnv().get_template( self.getTemplateFileName( tpl ) )
		return( template.render( repoObj=repoObj, **kwargs ) )


	def renderEmail(self, skel, tpl, dests ):
		"""
			Renders an email.
			@param skel: Skeleton or Dictionary which data to supply to the template
			@type skel: Skeleton or Dict
			@param tpl: Name of the email-template to use. If this string is longer than 100 characters, this string is interpreted as the template contents insted of its filename.
			@type tpl: String
			@param dests: Destination email-address
			@type dests: String
		"""
		headers = {}
		user = session.current.get("user")
		if isinstance( skel, Skeleton ):
			res = self.collectSkelData( skel )
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
		for line in data.splitlines():
			if body==False:
				if not line or not ":" in line or not len( line.split(":") ) == 2:
					body=""
				else:
					k,v = line.split(":")
					headers[ k.lower() ] = v
			if body != False:
				body += line+"\n"
		return( headers, body  )
