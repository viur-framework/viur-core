# -*- coding: utf-8 -*-
from jinja2 import Environment, FileSystemLoader, ChoiceLoader
from server.render.jinja2 import default
from server import request, session
import os, StringIO
import xhtml2pdf
import xhtml2pdf.pisa as pisa

class Render( default ):
	
	pdfPath = "pdf"
	
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
		if "pdfPath" in dir( self ):
			pdfPath = self.pdfPath
		else:
			pdfPath = "pdf"
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
		for fn in fnames: #Check the pdffolder of the application
			if os.path.isfile( os.path.join( os.getcwd(), pdfPath, fn ) ):
				return( fn )
		for fn in fnames: #Check the templatefolder of the application
			if os.path.isfile( os.path.join( os.getcwd(), htmlpath, fn ) ):
				return( fn )
		for fn in fnames: #Check the PDF fallback
			if os.path.isfile( os.path.join( os.getcwd(), "server", "template", "pdf",  fn ) ):
				return( fn )
		for fn in fnames: #Check the fallback
			if os.path.isfile( os.path.join( os.getcwd(), "server", "template", "html", fn ) ):
				return( fn )
		raise errors.NotFound( "Template %s not found." % template )
	
	def getLoaders(self):
		"""
			Return the List of Jinja2-Loaders which should be used.
			May be overriden to provide an alternative loader
			(eg. fetch templates from the datastore).
		"""
		if "pdfPath" in dir( self ):
			pdfPath = self.pdfPath
		else:
			pdfPath = "pdf"
		if "htmlpath" in dir( self ):
			htmlpath = self.htmlpath
		else:
			htmlpath = "html/"
		return( ChoiceLoader( [	FileSystemLoader( pdfPath ),
							FileSystemLoader( htmlpath ),
							FileSystemLoader( "server/template/pdf/" ), 
							FileSystemLoader( "server/template/html/" )
							] ) )
	
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
		htmlRes = super( Render, self).add( skel, tpl, *args, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )
		
	
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
		htmlRes = super( Render, self).edit( skel, tpl, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )
	
	def addItemSuccess (self, id, skel, *args, **kwargs ):
		"""
			Render an page, informing that the entry has been successfully created.
			@param id: Urlsafe key of the new entry
			@type id: String
			@param skel: Skeleton which contains the data of the new entity
			@type skel: Skeleton
		"""
		htmlRes = super( Render, self).addItemSuccess(  id, skel, *args, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )

	def editItemSuccess (self, skel, *args, **kwargs ):
		"""
			Render an page, informing that the entry has been successfully modified.
			@param skel: Skeleton which contains the data of the new entity
			@type skel: Skeleton
		"""
		htmlRes = super( Render, self).editItemSuccess( skel, *args, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )
	
	def deleteSuccess (self, *args, **kwargs ):
		"""
			Render an page, informing that the entry has been successfully deleted.
			Parameters depends on the application calling this:
			List and Hierachy pass the id of the deleted Entry, while Tree passes the rootNode and path.
		"""
		htmlRes = super( Render, self).deleteSuccess( *args, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )
	
	def list( self, skellist, tpl=None, **kwargs ):
		"""
			Renders a list of entries.
			@param skellist: Skellist-instance which the entries to display
			@type skellist: Skellist
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		htmlRes = super( Render, self).list( skellist, tpl, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )
	
	def listRootNodes(self, repos, tpl=None, **kwargs ):
		"""
			Renders a list of available repositories.
			@param repos: List of repositories ( Dictionaries with "key"=>Repo-Key and "name"=>Repo-Name )
			@type repos: List
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		htmlRes = super( Render, self).listRootNodes( repos, tpl, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )
	
	def view( self, skel, tpl=None, **kwargs ):
		"""
			Renders a page to display a single item
			@param skel: Skeleton which contains the data of the entity
			@type skel: Skeleton
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		htmlRes = super( Render, self).view( skel, tpl, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )
	
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
		htmlRes = super( Render, self).listRootNodeContents( subdirs, entries, tpl, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )

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
		htmlRes = super( Render, self).addDirSuccess( rootNode,  path, dirname, *args, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )

	def renameSuccess(self, rootNode, path, src, dest, *args, **kwargs ):
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
		htmlRes = super( Render, self).renameSuccess( rootNode, path, src, dest, *args, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )

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
		htmlRes = super( Render, self).copySuccess( srcrepo, srcpath, name, destrepo, destpath, type, deleteold, *args, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )


	def reparentSuccess(self, repoObj, tpl=None, **kwargs ):
		"""
			Renders a page informing that the item was successfully moved.
			@param repoObj: ndb.Expando instance of the item that was moved
			@type repoObj: ndb.Expando
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		htmlRes = super( Render, self).reparentSuccess( repoObj, tpl, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )

	def setIndexSuccess(self, dbobj, tpl=None, *args, **kwargs ):
		"""
			Renders a page informing that the items sortindex was successfully changed.
			@param repoObj: ndb.Expando instance of the item that was changed
			@type repoObj: ndb.Expando
			@param tpl: Name of an different template, which should be used instead of the default one
			@param: tpl: String
		"""
		htmlRes = super( Render, self).setIndexSuccess( dbobj, tpl, *args, **kwargs )
		result = StringIO.StringIO()
		pdf = pisa.CreatePDF( StringIO.StringIO(htmlRes.encode('ascii', 'xmlcharrefreplace')), result )
		try:
			name = str(skel.name.value)
		except:
			name = "export"
		name = "".join( [ x for x in name.lower() if x in "abcdefghijklmnopqrstuvwxyz1234567890 "] )
		request.current.get().response.headers['Content-Disposition'] = "attachment; filename=\"%s.pdf\"" % name
		request.current.get().response.headers['Content-Type'] = "application/pdf"
		return( result.getvalue() )

