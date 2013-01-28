from google.appengine.ext import db
from time import time
from google.appengine.api import backends
from server.update import checkUpdate
from server.config import conf, sharedConf
from server import errors, request
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.api import taskqueue
from google.appengine.ext.deferred import PermanentTaskFailure
import json
import logging
import os


_periodicTasks = {}
_callableTasks = {}
_periodicTaskID = 1L #Used to determine bound functions


class _DeferredTaskEntity(db.Model):
	"""Datastore representation of a deferred task.
	
	This is used in cases when the deferred task is too big to be included as
	payload with the task queue entry.
	"""
	data = db.BlobProperty(required=True)

class CallableTaskBase:
	"""Base class for user-callable tasks.
	Must be subclassed.
	"""
	id = None
	name = None
	descr = None
	direct = False #If true, this task will be called instantly (60 sec timelimit!), else it will be defered to the backend
	entityName = "server-task"
	
	def canCall( self ):
		"""Checks wherever the current user can execute this task
		@returns bool
		"""
		return( users.is_current_user_admin() )
		
	def dataSkel(self):
		return( None )
		
	
	def execute(self):
		raise NotImplemented()
	
class TaskHandler:
	"""Task Handler.
	Handles calling of Tasks (queued and periodic), and performs updatececks
	Do not Modify. Do not Subclass.
	"""
	adminInfo = None

	def __init__(self, modulName, modulPath ):
		pass
	
	def findBoundTask( self, task, obj=None, depth=0 ):
		"""
			Tries to locate the instance, this function belongs to.
			If it succeeds in finding it, it returns the function and its instance (-> its "self").
			Otherwise, None is returned.
			@param task: A callable decorated with @PeriodicTask
			@type task: callable
			@param obj: Object, which will be scanned in the current iteration. None means start at conf["viur.mainApp"].
			@type obj: object
			@param depth: Current iteration depth.
			@type depth: int
		"""
		if depth>3 or not "periodicTaskID" in dir( task ): #Limit the maximum amount of recursions
			return( None )
		obj = obj or conf["viur.mainApp"]
		for attr in dir( obj ):
			if attr.startswith("_"):
				continue
			try:
				v = getattr( obj, attr )
			except AttributeError:
				continue
			if callable( v ) and "periodicTaskID" in dir( v ) and str(v.periodicTaskID)==str(task.periodicTaskID):
				return( v, obj )
			if not isinstance( v, basestring ) and not callable( v ):
				res = self.findBoundTask( task, v, depth+1 )
				if res:
					return( res )
		return( None )
	
	def deferred(self, *args, **kwargs ):
		"""
			This catches one defered call and routes it to its destination
		"""
		req = request.current.get().request
		if 'X-AppEngine-TaskName' not in req.headers:
			logging.critical('Detected an attempted XSRF attack. The header "X-AppEngine-Taskname" was not set.')
			raise errors.Forbidden()
		in_prod = ( not req.environ.get("SERVER_SOFTWARE").startswith("Devel") )
		if in_prod and req.environ.get("REMOTE_ADDR") != "0.1.0.2":
			logging.critical('Detected an attempted XSRF attack. This request did not originate from Task Queue.')
			req.set_status(403)
			raise errors.Forbidden()
		headers = ["%s:%s" % (k, v) for k, v in req.headers.items() if k.lower().startswith("x-appengine-")]
		cmd, data = json.loads( req.body )
		dbObj = None
		if cmd=="fromdb":
			dbObj = _DeferredTaskEntity.get( data )
			cmd, data = json.loads( dbObj.data )
		if cmd=="rel":
			funcPath, args, kwargs = data
			caller = conf["viur.mainApp"]
			pathlist = [ x for x in funcPath.split("/") if x]
			for currpath in pathlist:
				assert currpath in dir( caller )
				caller = getattr( caller,currpath )
			try:
				caller( *args, **kwargs )
			except PermanentTaskFailure:
				if dbObj:
					dbObj.delete()
			except Exception as e:
				logging.exception( e )
				raise errors.RequestTimeout() #Task-API should retry
			else:
				if dbObj:
					dbObj.delete()
	deferred.exposed=True
	
	def index(self, *args, **kwargs):
		global _callableTasks, _periodicTasks
		from server.utils import generateExpandoClass
		#if not backends.get_backend(): #Assert this only runs on a backend server (No Timelimit)
		#	return
		logging.debug("Starting maintenance-run")
		checkUpdate() #Let the update-module verify the database layout first
		logging.debug("Updatecheck complete")
		for task,intervall in _periodicTasks.items(): #Call all periodic tasks
			res = self.findBoundTask( task )
			if res: #Its bound, call it this way :)
				t, s = res
				t( s )
				continue
			task() #It seems it wasnt bound - call it as a static method
		logging.debug("Periodic tasks complete")
		for currentTask in generateExpandoClass("server-tasks").query().iter(): #Look for queued tasks
			currentTask.key.delete()
			if currentTask.taskid in _callableTasks.keys():
				task = _callableTasks[ currentTask.taskid ]()
				tmpDict = {}
				for k in currentTask._properties.keys():
					if k == "taskid":
						continue
					logging.error( getattr( currentTask, k ) )
					tmpDict[ k ] = json.loads( getattr( currentTask, k ) )
				try:
					task.execute( **tmpDict )
				except Exception as e:
					logging.error("Error executing Task")
					logging.exception( e )
		logging.debug("Scheduled tasks complete")
	index.exposed=True
	
	def list(self, *args, **kwargs ):
		"""Lists all user-callabe tasks which are callable by this user"""
		global _callableTasks
		class extList( list ):
			pass
		res = extList( [{"id": x.id, "name":_(x.name), "descr":_(x.descr) } for x in _callableTasks.values() if x().canCall()] )
		res.cursor = None
		return( self.render.list( res ) )
	list.exposed=True
	
	def execute(self, taskID, *args, **kwargs ):
		"""Queues a specific task for the next maintenance run"""
		global _callableTasks
		from server.utils import validateSecurityKey, generateExpandoClass
		if taskID in _callableTasks.keys():
			task = _callableTasks[ taskID ]()
		else:
			return
		if not task.canCall():
			raise errors.Unauthorized()
		skel = task.dataSkel()
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if not skel.fromClient( kwargs ) or len(kwargs)==0 or skey=="" or ("bounce" in list(kwargs.keys()) and kwargs["bounce"]=="1"):
			return( self.render.add( skel ) )
		if not validateSecurityKey( skey ):
			raise errors.PreconditionFailed()
		if task.direct:
			task.execute( **skel.getValues() )
		else:
			dbObj = generateExpandoClass("server-tasks")()
			for k, v in skel.getValues().items():
				setattr( dbObj, k, json.dumps(v) )
			dbObj.taskid = taskID
			id = dbObj.put()
		return self.render.addItemSuccess( None, skel )
	execute.exposed = True
	
TaskHandler.admin = True	
TaskHandler.jinja2 = True

## Decorators ##

def noRetry( f ):
	"""Prevents a defered Function from beeing called a second time"""
	@wraps( f )
	def wrappedFunc( *args,  **kwargs ):
		try:
			f( *args,  **kwargs )
		except:
			raise deferred.PermanentTaskFailure()
	return( wrappedFunc )

def callDefered( func ):
	"""
		This is a decorator, wich allways calls the function defered.
		Unlike Googles implementation, this one works (with bound functions)
	"""
	def mkDefered( func, self, *args,  **kwargs ):
		if "HTTP_X_APPENGINE_TASKRETRYCOUNT".lower() in [x.lower() for x in os.environ.keys()]: #This is the defered call
			return( func( self, *args, **kwargs ) )
		else:
			funcPath = "%s/%s" % (self.modulPath, func.func_name )
			taskargs = dict((x, kwargs.pop(("_%s" % x), None))  for x in ("countdown", "eta", "name", "target", "retry_options"))
			taskargs["url"] = "/_tasks/deferred"
			transactional = kwargs.pop("_transactional", False)
			taskargs["headers"] = {"Content-Type": "application/octet-stream"}
			queue = "default"
			pickled = json.dumps( ("rel", (funcPath, args, kwargs) ) )
			try:
				task = taskqueue.Task(payload=pickled, **taskargs)
				return task.add(queue, transactional=transactional)
			except taskqueue.TaskTooLargeError:
				key = _DeferredTaskEntity(data=pickled).put()
				pickled = json.dumps( ("fromdb", str(key) ) )
				task = taskqueue.Task(payload=pickled, **taskargs)
			return task.add(queue)
	return( lambda *args, **kwargs: mkDefered( func, *args, **kwargs) )


def PeriodicTask( intervall ):
	"""Decorator to call a function periodic during maintenance.
	The intervall-parameter is currently ignored"""
	def mkDecorator( fn ):
		global _periodicTasks, _periodicTaskID
		_periodicTasks[ fn ] = intervall
		fn.periodicTaskID = _periodicTaskID
		_periodicTaskID += 1
		return( fn )
	return( mkDecorator )

def CallableTask( fn ):
	"""Marks a Class as representig a user-callabe Task.
	It *should* extend CallableTaskBase and *must* provide
	its API
	"""
	global _callableTasks
	_callableTasks[ fn.id ] = fn
	return( fn )


## Tasks ##


@CallableTask
class DisableApplicationTask( CallableTaskBase ):
	"""
		Allows en- or disabling the application.
	"""
	id = "viur-disable-server"
	name = "Enable or disable the application"
	descr = "This will enable or disable the application."
	direct = True #If true, this task will be called instantly (60 sec timelimit!), else it will be defered to the backend
	entityName = "server-task"
	
	def canCall( self ):
		"""
			Checks wherever the current user can execute this task
			@returns bool
		"""
		return( users.is_current_user_admin() )

	def dataSkel( self ):
		from server.bones import booleanBone, stringBone
		from server.skeleton import Skeleton
		skel = Skeleton( self.entityName )
		skel.active = booleanBone( descr="Application active", required=True )
		skel.descr = stringBone( descr="Reason for disabling", required=False )
		return( skel )
	
	def execute(self, active, descr, *args, **kwargs):
		if not active:
			if descr:
				sharedConf["viur.disabled"] = descr
			else:
				sharedConf["viur.disabled"] = True
		else:
			sharedConf["viur.disabled"] = False
