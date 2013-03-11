# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server.applications.hierarchy import Hierarchy, HierarchySkel
from server.applications.list import List
from server.bones import *
from server import db
from server import session, errors
from server.indexes import IndexMannager
from google.appengine.ext import deferred
from server.skellist import Skellist
from server import utils, request, tasks
import logging

class ForumSkel( HierarchySkel ):
	kindName = "forum"
	name = stringBone( descr="Name", required=True )
	descr = textBone( descr="Descriptions", required=True )
	readaccess = selectOneBone( descr="Read-Access", values={"admin":"Admin only", "users":"Registered users", "all":"everyone" } )
	writeaccess = selectOneBone( descr="Write-Access", values={"admin":"Admin only", "users":"Registered users", "all":"everyone" } )
	
	
class PostSkel( Skeleton ):
	kindName = "forumpost"
	name = stringBone( descr="Name", required=True )
	descr = textBone( descr="Message", required=True )
	thread = stringBone( descr="Thread", type="forumposts", visible=False, indexed=True, required=False )
	user = userBone( descr="User", creationMagic=True, visible=False, required=False )
	creationdate = dateBone( descr="created at", readOnly=True, visible=False, creationMagic=True, indexed=True, localize=True )

class ThreadSkel( PostSkel ):
	kindName = "forumthread"
	forum = hierarchyBone( descr="Forum", type="forum",  visible=False, required=True )
	fid = stringBone( descr="ForumID", visible=False, indexed=True, readOnly=True )
	thread = None

	def preProcessSerializedData( self, dbfilter ):
		if self.forum.value:
			dbfilter[ "fid" ] = self.forum.value["id"]
		return( dbfilter )


class Forum( Hierarchy ): 
	adminInfo = {	"name": "Forum", #Name of this modul, as shown in Apex (will be translated at runtime)
				"handler": "hierarchy",  #Which handler to invoke
				"icon": "icons/modules/forum.png", #Icon for this modul
				"formatstring": "$(name)", 
				}
	indexMgr = IndexMannager()
	addSkel = ForumSkel
	editSkel = ForumSkel
	viewSkel = ForumSkel
	threadSkel = ThreadSkel
	postSkel = PostSkel
	listTemplate = "forum_list"
	viewForumTemplate = "forum_thread_list"
	viewThreadTemplate = "forum_post_list"
	addThreadTemplate = "forum_thread_add"
	addPostTemplate = "forum_post_add"
	addSuccessTemplate = "forum_add_success"
	editThreadTemplate = "forum_thread_edit"
	editPostTemplate = "forum_post_edit"
	
	def jinjaEnv(self, env ):
		env = super( Forum, self ).jinjaEnv( env )
		env.globals["getCurrentForum"] = self.getCurrentForum
		env.globals["canAddThread"] = self.canAddThread
		env.globals["canAddPost"] = self.canAddPost
		env.globals["canEditThread"] = self.canEditThread
		env.globals["canEditPost"] = self.canEditPost
		env.globals["canDeletePost"] = self.canDeletePost
		env.globals["canDeleteThread"] = self.canDeleteThread
		return( env )
		
	def getCurrentForum( self ):
		kwargs = request.current.get().kwargs
		if "threadid" in kwargs.keys():
			thread = self.threadSkel()
			if not thread.fromDB( kwargs["threadid"] ):
				return( None )
			return( thread.forum.value )
		elif "forumid" in kwargs.keys():
			forum = self.viewSkel()
			if not forum.fromDB( kwargs["forumid"] ):
				return( False )
			return( {"id": forum.id.value, "name": forum.name.value } )
		return( None )
	
	def index(self, *args, **kwargs):
		repo = self.ensureOwnModulRootNode()
		return( self.list( str(repo.key())) )
	index.exposed=True

	def getAvailableRootNodes( self, *args, **kwargs ):
		repo = self.ensureOwnModulRootNode()
		return( [{"name":u"Forum", "key": str(repo.key()) }] )
	
	def viewForum(self, forumid, page=0, *args, **kwargs ):
		if not self.canView( forumid ):
			raise( errors.Unauthorized() )
		queryObj = self.threadSkel().all().mergeExternalFilter( {"fid": forumid, "orderby":"creationdate", "orderdir":"1","amount": "10" })    #, "amount":"10", "orderby":"creationdate", "orderdir":"1"
		start_cursor=self.indexMgr.cursorForQuery( queryObj, page )
		mylist = queryObj.cursor( start_cursor ).fetch()
		return( self.render.list( mylist, tpl=self.viewForumTemplate, pages=self.indexMgr.getPages( queryObj )  ) )
	viewForum.exposed=True

	def viewThread(self, threadid, page=0, *args, **kwargs ):
		thread = self.threadSkel()
		if not thread.fromDB( threadid ) or not self.canView( thread.forum.value["id"] ):
			raise( errors.Unauthorized() )
		queryObj =self.postSkel().all().mergeExternalFilter( {"thread":threadid, "amount":"10", "orderby":"creationdate", "orderdir":"0" } )
		if not queryObj:
			raise( errors.Unauthorized() )
		mylist = queryObj.cursor( self.indexMgr.cursorForQuery( queryObj, page ) ).fetch()
		return( self.render.list( mylist, tpl=self.viewThreadTemplate, pages=self.indexMgr.getPages( queryObj ) ) )
	viewThread.exposed=True
	
	def addThread( self, forum, *args, **kwargs ):
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if not self.canAddThread( forum ):
			raise errors.Unauthorized()
		skel = self.threadSkel()
		kwargs["forum"] = forum
		if not skel.fromClient( kwargs ) or len(kwargs)==0 or skey=="" or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.add( skel, tpl=self.addThreadTemplate ) )
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		id = skel.toDB( )
		#Now add the first post to this thread
		postSkel = self.postSkel()
		tmp = kwargs.copy()
		tmp["thread"] = str(id)
		postSkel.fromClient( tmp )
		postSkel.toDB()
		#Refresh the index
		queryObj = self.threadSkel().all().mergeExternalFilter( {"fid": skel.forum.value["id"],"orderby":"creationdate", "orderdir":"1", "amount":"10"} )  #Build the initial one
		self.indexMgr.refreshIndex( queryObj )
		self.onItemAdded( id, skel )
		return self.render.addItemSuccess( id, skel )
	addThread.exposed = True
	
	def addPost( self, thread, *args, **kwargs ):
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if not self.canAddPost( thread ):
			raise errors.Unauthorized()
		skel = self.postSkel()
		kwargs["thread"] = thread
		if not skel.fromClient( kwargs ) or len(kwargs)==0 or skey=="" or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.add( skel, tpl=self.addPostTemplate ) )
		threadSkel = self.threadSkel()
		if not utils.validateSecurityKey( skey ) or not self.threadSkel().fromDB( skel.thread.value ): #Maybe stale thread
			raise errors.PreconditionFailed()
		id = skel.toDB( )
		#Refresh the index
		queryObj = self.postSkel().all().mergeExternalFilter( {"thread":skel.thread.value, "amount":"10", "orderby":"creationdate", "orderdir":"0" } )
		self.indexMgr.refreshIndex( queryObj )
		self.onItemAdded( id, skel )
		return self.render.addItemSuccess( id, skel )
	addPost.exposed = True

	def deletePost(self, post, skey,  **kwargs ):
		if not self.canDeletePost( post ):
			raise errors.Unauthorized()
		skel = self.postSkel()
		if not utils.validateSecurityKey( skey ) or not skel.fromDB( post ):
			raise errors.PreconditionFailed()
		skel.delete( post )
		#Refresh the index
		queryObj = utils.buildDBFilter( self.postSkel() ,  {"thread":skel.thread.value}) #Build the initial one
		self.indexMgr.refreshIndex( queryObj )
		self.onItemDeleted( skel )
		self.checkForEmptyThread( skel.thread.value )
		return( self.render.deleteSuccess( skel ) )
	deletePost.exposed=True
	
	def deleteThread(self, thread, skey, **kwargs ):
		if not self.canDeleteThread( thread ):
			raise errors.Unauthorized()
		skel = self.threadSkel()
		if not utils.validateSecurityKey( skey ) or not skel.fromDB( thread ):
			raise errors.PreconditionFailed()
		skel.delete( thread )
		#Refresh the index
		queryObj = utils.buildDBFilter( self.threadSkel() ,  { "fid": skel.forum.value["id"], "amount":"10" }) #Build the initial one
		self.indexMgr.refreshIndex( queryObj )
		self.deleteStalePosts( thread )
		return( self.render.deleteSuccess( skel ) )
	deleteThread.exposed = True
		
	@tasks.callDefered
	def deleteStalePosts(self, thread ):
		"""
			Remove posts which belong to a thread we just deleted
		"""
		postSkel = self.postSkel()
		for post in db.Query( postSkel.kindName ).filter( "thread", thread ).iter():
			postSkel.delete( str( post.key() ) )

	@tasks.callDefered
	def checkForEmptyThread(self, thread ): #Fixme: We still have a race-condition here...
		post = db.Query( self.postSkel() ).filter( "thread", thread ).get()
		if not post:
			skel = self.threadSkel()
			if not skel.fromDB( thread ):
				return
			skel.delete( thread )
			#Refresh the index
			queryObj = db.Query( self.threadSkel().kindName )
			queryObj[ "fid" ] = skel.forum.value["id"] #Build the initial one
			self.indexMgr.refreshIndex( queryObj )
	
	def editThread(self, id, skey="",  *args, **kwargs ):
		if not self.canEditThread( id ):
			raise errors.Unauthorized()
		skel = self.threadSkel()
		if not skel.fromDB( id ):
			raise errors.PreconditionFailed()
		if len(kwargs)==0 or skey=="" or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.edit( skel, tpl=self.editThreadTemplate ) )
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		skel.toDB( id )
		self.onItemEdited( id, skel )
		return self.render.editItemSuccess( skel )
	editThread.exposed=True
	
	def editPost(self, id, skey="",  *args, **kwargs ):
		if not self.canEditPost( id ):
			raise errors.Unauthorized()
		skel = self.postSkel()
		if not skel.fromDB( id ):
			raise errors.PreconditionFailed()
		if len(kwargs)==0 or skey=="" or not skel.fromClient( kwargs ) or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.edit( skel, tpl=self.editPostTemplate ) )
		if not utils.validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		skel.toDB( id )
		self.onItemEdited( id, skel )
		return self.render.editItemSuccess( skel )
	editPost.exposed=True

	def canView(self, id):
		skel = self.viewSkel()
		user = utils.getCurrentUser()
		if not skel.fromDB( id ):
			return( False )
		if skel.readaccess.value == "all":
			return( True )
		elif skel.readaccess.value == "users" and user:
			return( True )
		elif skel.readaccess.value=="admin" and user and "root" in user["access"]:
			return( True )
		return( False )
		
	def canList(self, id):
		skel = self.viewSkel()
		user = utils.getCurrentUser()
		if not skel.fromDB( id ):
			return( False )
		if skel.readaccess.value == "all":
			return( True )
		elif skel.readaccess.value == "users" and user:
			return( True )
		elif skel.readaccess.value=="admin" and user and "root" in user["access"]:
			return( True )
		return( False )
		
	def canAddThread(self, forum):
		skel = self.editSkel()
		user = utils.getCurrentUser()
		if not skel.fromDB( forum ):
			return( False )
		if skel.writeaccess.value == "all":
			return( True )
		elif skel.writeaccess.value == "users" and user:
			return( True )
		elif skel.writeaccess.value=="admin" and user and "root" in user["access"]:
			return( True )
		return( False )

	def canAddPost(self, thread):
		threadSkel = self.threadSkel()
		if not threadSkel.fromDB( thread ):
			return( False )
		if not threadSkel.forum.value:
			return( False )
		skel = self.editSkel()
		user = utils.getCurrentUser()
		if not skel.fromDB( threadSkel.forum.value["id"] ):
			return( False )
		if skel.writeaccess.value == "all":
			return( True )
		elif skel.writeaccess.value == "users" and user:
			return( True )
		elif skel.writeaccess.value=="admin" and user and "root" in user["access"]:
			return( True )
		return( False )

	def canEditThread(self, thread ):
		user = utils.getCurrentUser()
		if user and "root" in user["access"]:
			return( True )
		return( False )
		
	def canEditPost(self, post ):
		user = utils.getCurrentUser()
		if user and "root" in user["access"]:
			return( True )
		return( False )

	def canDeletePost(self, post ):
		user = utils.getCurrentUser()
		if user and "root" in user["access"]:
			return( True )
		return( False )

	def canDeleteThread(self, thread ):
		user = utils.getCurrentUser()
		if user and "root" in user["access"]:
			return( True )
		return( False )

Forum.jinja2 = True
Forum.ops = True

	


