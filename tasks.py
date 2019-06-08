# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from server.update import checkUpdate
from server.config import conf, sharedConf
from server import errors, request
from google.appengine.api import users
from google.appengine.api import taskqueue
from google.appengine.ext.deferred import PermanentTaskFailure
from server import db
from functools import wraps
import json
import logging
import os, sys

_periodicTasks = {}
_callableTasks = {}
_deferedTasks = {}
_startupTasks = []
_periodicTaskID = 1L  # Used to determine bound functions


class CallableTaskBase:
	"""
		Base class for user-callable tasks.
		Must be subclassed.
	"""
	key = None  # Unique identifier for this task
	name = None  # Human-Readable name
	descr = None  # Human-Readable description
	kindName = "server-task"

	def canCall(self):
		"""
			Checks wherever the current user can execute this task
			:returns: bool
		"""
		return (False)

	def dataSkel(self):
		"""
			If additional data is needed, return a skeleton-instance here.
			These values are then passed to *execute*.
		"""
		return (None)

	def execute(self):
		"""
			The actual code that should be run goes here.
		"""
		raise NotImplemented()


class TaskHandler:
	"""
		Task Handler.
		Handles calling of Tasks (queued and periodic), and performs updatececks
		Do not Modify. Do not Subclass.
	"""
	adminInfo = None
	retryCountWarningThreshold = 25

	def __init__(self, moduleName, modulePath):
		pass

	def findBoundTask(self, task, obj=None, depth=0):
		"""
			Tries to locate the instance, this function belongs to.
			If it succeeds in finding it, it returns the function and its instance (-> its "self").
			Otherwise, None is returned.
			:param task: A callable decorated with @PeriodicTask
			:type task: callable
			:param obj: Object, which will be scanned in the current iteration. None means start at conf["viur.mainApp"].
			:type obj: object
			:param depth: Current iteration depth.
			:type depth: int
		"""
		if depth > 3 or not "periodicTaskID" in dir(task):  # Limit the maximum amount of recursions
			return (None)
		obj = obj or conf["viur.mainApp"]
		for attr in dir(obj):
			if attr.startswith("_"):
				continue
			try:
				v = getattr(obj, attr)
			except AttributeError:
				continue
			if callable(v) and "periodicTaskID" in dir(v) and str(v.periodicTaskID) == str(task.periodicTaskID):
				return (v, obj)
			if not isinstance(v, basestring) and not callable(v):
				res = self.findBoundTask(task, v, depth + 1)
				if res:
					return (res)
		return (None)

	def deferred(self, *args, **kwargs):
		"""
			This catches one defered call and routes it to its destination
		"""
		from server import session
		from server import utils
		global _deferedTasks

		req = request.current.get().request
		if 'X-AppEngine-TaskName' not in req.headers:
			logging.critical('Detected an attempted XSRF attack. The header "X-AppEngine-Taskname" was not set.')
			raise errors.Forbidden()
		in_prod = (not req.environ.get("SERVER_SOFTWARE").startswith("Devel"))
		if in_prod and req.environ.get("REMOTE_ADDR") != "0.1.0.2":
			logging.critical('Detected an attempted XSRF attack. This request did not originate from Task Queue.')
			raise errors.Forbidden()
		# Check if the retry count exceeds our warning threshold
		retryCount = req.headers.get("X-Appengine-Taskretrycount", None)
		if retryCount:
			if int(retryCount) == self.retryCountWarningThreshold:
				utils.sendEMailToAdmins("Deferred task retry count exceeded warning threshold",
										"Task %s will now be retried for the %sth time." % (
											req.headers.get("X-Appengine-Taskname", ""),
											retryCount))
		cmd, data = json.loads(req.body)
		try:
			funcPath, args, kwargs, env = data
		except ValueError:  # We got an old call without an frozen environment
			env = None
			funcPath, args, kwargs = data
		if env:
			if "user" in env and env["user"]:
				session.current["user"] = env["user"]
			if "lang" in env and env["lang"]:
				request.current.get().language = env["lang"]
			if "custom" in env and conf["viur.tasks.customEnvironmentHandler"]:
				# Check if we need to restore additional enviromental data
				assert isinstance(conf["viur.tasks.customEnvironmentHandler"], tuple) \
					   and len(conf["viur.tasks.customEnvironmentHandler"]) == 2 \
					   and callable(conf["viur.tasks.customEnvironmentHandler"][1]), \
					"Your customEnvironmentHandler must be a tuple of two callable if set!"
				conf["viur.tasks.customEnvironmentHandler"][1](env["custom"])
		if cmd == "rel":
			caller = conf["viur.mainApp"]
			pathlist = [x for x in funcPath.split("/") if x]
			for currpath in pathlist:
				if currpath not in dir(caller):
					logging.error("ViUR missed a deferred task! Could not resolve the path %s. Failed segment was %s",
								  funcPath, currpath)
					return
				caller = getattr(caller, currpath)
			try:
				caller(*args, **kwargs)
			except PermanentTaskFailure:
				pass
			except Exception as e:
				logging.exception(e)
				raise errors.RequestTimeout()  # Task-API should retry
		elif cmd == "unb":
			if not funcPath in _deferedTasks:
				logging.error("Ive missed a defered task! %s(%s,%s)" % (funcPath, str(args), str(kwargs)))
			try:
				_deferedTasks[funcPath](*args, **kwargs)
			except PermanentTaskFailure:
				pass
			except Exception as e:
				logging.exception(e)
				raise errors.RequestTimeout()  # Task-API should retry

	deferred.exposed = True

	def index(self, *args, **kwargs):
		global _callableTasks, _periodicTasks
		logging.debug("Starting maintenance-run")
		checkUpdate()  # Let the update-module verify the database layout first
		logging.debug("Updatecheck complete")
		for task, intervall in _periodicTasks.items():  # Call all periodic tasks
			if intervall:  # Ensure this task doesn't get called to often
				try:
					lastCall = db.Get(db.Key.from_path("viur-task-interval", task.periodicTaskName))
					if lastCall["date"] > datetime.now() - timedelta(minutes=intervall):
						logging.debug("Skipping task %s - Has already run recently." % task.periodicTaskName)
						continue
				except db.EntityNotFoundError:
					pass
			res = self.findBoundTask(task)
			if res:  # Its bound, call it this way :)
				t, s = res
				t(s)
			else:
				task()  # It seems it wasnt bound - call it as a static method
			logging.debug("Successfully called task %s" % task.periodicTaskName)
			if intervall:
				# Update its last-call timestamp
				entry = db.Entity("viur-task-interval", name=task.periodicTaskName)
				entry["date"] = datetime.now()
				db.Put(entry)
		logging.debug("Periodic tasks complete")
		for currentTask in db.Query("viur-queued-tasks").iter():  # Look for queued tasks
			db.Delete(currentTask.key())
			if currentTask["taskid"] in _callableTasks:
				task = _callableTasks[currentTask["taskid"]]()
				tmpDict = {}
				for k in currentTask.keys():
					if k == "taskid":
						continue
					tmpDict[k] = json.loads(currentTask[k])
				try:
					task.execute(**tmpDict)
				except Exception as e:
					logging.error("Error executing Task")
					logging.exception(e)
		logging.debug("Scheduled tasks complete")

	index.exposed = True

	def list(self, *args, **kwargs):
		"""Lists all user-callabe tasks which are callable by this user"""
		global _callableTasks

		class extList(list):
			pass

		res = extList(
			[{"key": x.key, "name": _(x.name), "descr": _(x.descr)} for x in _callableTasks.values() if x().canCall()])
		res.cursor = None
		res.baseSkel = {}
		return (self.render.list(res))

	list.exposed = True

	def execute(self, taskID, *args, **kwargs):
		"""Queues a specific task for the next maintenance run"""
		global _callableTasks
		from server import securitykey
		if taskID in _callableTasks:
			task = _callableTasks[taskID]()
		else:
			return
		if not task.canCall():
			raise errors.Unauthorized()
		skel = task.dataSkel()
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""
		if len(kwargs) == 0 or skey == "" or not skel.fromClient(kwargs) or (
				"bounce" in kwargs and kwargs["bounce"] == "1"):
			return self.render.add(skel)
		if not securitykey.validate(skey):
			raise errors.PreconditionFailed()
		task.execute(**skel.getValues())
		return self.render.addItemSuccess(skel)

	execute.exposed = True


TaskHandler.admin = True
TaskHandler.vi = True
TaskHandler.html = True


## Decorators ##

def noRetry(f):
	"""Prevents a deferred Function from beeing called a second time"""

	@wraps(f)
	def wrappedFunc(*args, **kwargs):
		try:
			f(*args, **kwargs)
		except Exception as e:
			logging.exception(e)
			raise PermanentTaskFailure()

	return (wrappedFunc)


def callDeferred(func):
	"""
		This is a decorator, which allways calls the function deferred.
		Unlike Googles implementation, this one works (with bound functions)
	"""
	if "viur_doc_build" in dir(sys):
		return (func)
	__undefinedFlag_ = object()

	def mkDefered(func, self=__undefinedFlag_, *args, **kwargs):
		from server.utils import getCurrentUser
		try:
			req = request.current.get()
		except:  # This will fail for warmup requests
			req = None
		if req is not None and "HTTP_X_APPENGINE_TASKRETRYCOUNT".lower() in [x.lower() for x in
																			 os.environ.keys()] and not "DEFERED_TASK_CALLED" in dir(
				req):  # This is the deferred call
			req.DEFERED_TASK_CALLED = True  # Defer recursive calls to an deferred function again.
			if self is __undefinedFlag_:
				return func(*args, **kwargs)
			else:
				return func(self, *args, **kwargs)
		else:
			try:
				funcPath = "%s/%s" % (self.modulePath, func.func_name)
				command = "rel"
			except:
				funcPath = "%s.%s" % (func.__name__, func.__module__)
				if self != __undefinedFlag_:
					args = (self,) + args  # Reappend self to args, as this function is (hopefully) unbound
				command = "unb"
			taskargs = dict(
				(x, kwargs.pop(("_%s" % x), None)) for x in ("countdown", "eta", "name", "target", "retry_options"))
			taskargs["url"] = "/_tasks/deferred"
			transactional = kwargs.pop("_transactional", False)
			taskargs["headers"] = {"Content-Type": "application/octet-stream"}
			queue = kwargs.pop("_queue", "default")
			# Try to preserve the important data from the current environment
			env = {"user": None}
			usr = getCurrentUser()
			if usr:
				env["user"] = {"key": usr["key"],
							   "name": usr["name"],
							   "access": usr["access"]}
			try:
				env["lang"] = request.current.get().language
			except AttributeError:  # This isn't originating from a normal request
				pass
			if conf["viur.tasks.customEnvironmentHandler"]:
				# Check if this project relies on additional environmental variables and serialize them too
				assert isinstance(conf["viur.tasks.customEnvironmentHandler"], tuple) \
					   and len(conf["viur.tasks.customEnvironmentHandler"]) == 2 \
					   and callable(conf["viur.tasks.customEnvironmentHandler"][0]), \
					"Your customEnvironmentHandler must be a tuple of two callable if set!"
				env["custom"] = conf["viur.tasks.customEnvironmentHandler"][0]()
			pickled = json.dumps((command, (funcPath, args, kwargs, env)))
			task = taskqueue.Task(payload=pickled, **taskargs)
			return task.add(queue, transactional=transactional)

	global _deferedTasks
	_deferedTasks["%s.%s" % (func.__name__, func.__module__)] = func
	return (lambda *args, **kwargs: mkDefered(func, *args, **kwargs))


def PeriodicTask(intervall):
	"""
		Decorator to call a function periodic during maintenance.
		Intervall defines a lower bound for the call-frequency for this task;
		it will not be called faster than each intervall minutes.
		(Note that the actual delay between two sequent might be much larger)
		:param intervall: Call at most every intervall minutes. 0 means call as often as possible.
		:type intervall: int
	"""

	def mkDecorator(fn):
		global _periodicTasks, _periodicTaskID
		_periodicTasks[fn] = intervall
		fn.periodicTaskID = _periodicTaskID
		fn.periodicTaskName = "%s.%s" % (fn.__module__, fn.__name__)
		_periodicTaskID += 1
		return (fn)

	return (mkDecorator)


def CallableTask(fn):
	"""Marks a Class as representing a user-callable Task.
	It *should* extend CallableTaskBase and *must* provide
	its API
	"""
	global _callableTasks
	_callableTasks[fn.key] = fn
	return (fn)


def StartupTask(fn):
	"""
		Functions decorated with this are called shortly at instance startup.
		It's *not* guaranteed that they actually run on the instance that just started up!
		Wrapped functions must not take any arguments.
	"""
	global _startupTasks
	_startupTasks.append(fn)
	return (fn)


@callDeferred
def runStartupTasks():
	"""
		Runs all queued startupTasks.
		Do not call directly!
	"""
	global _startupTasks
	for st in _startupTasks:
		st()


## Tasks ##


@CallableTask
class DisableApplicationTask(CallableTaskBase):
	"""
		Allows en- or disabling the application.
	"""
	key = "viur-disable-server"
	name = "Enable or disable the application"
	descr = "This will enable or disable the application."
	kindName = "server-task"

	def canCall(self):
		"""
			Checks wherever the current user can execute this task
			:returns: bool
		"""
		return (users.is_current_user_admin())

	def dataSkel(self):
		from server.bones import booleanBone, stringBone
		from server.skeleton import Skeleton
		skel = Skeleton(self.kindName)
		skel.active = booleanBone(descr="Application active", required=True)
		skel.descr = stringBone(descr="Reason for disabling", required=False)
		return (skel)

	def execute(self, active, descr, *args, **kwargs):
		if not active:
			if descr:
				sharedConf["viur.disabled"] = descr
			else:
				sharedConf["viur.disabled"] = True
		else:
			sharedConf["viur.disabled"] = False
