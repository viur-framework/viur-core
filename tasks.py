from google.appengine.ext import db
from time import time
from google.appengine.api import backends
from server.update import checkUpdate
from server.config import conf, sharedConf
from google.appengine.api import users
import json
import logging


_periodicTasks = {}
_callableTasks = {}
_periodicTaskID = 1L #Used to determine bound functions

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
					logging.error( e )
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
