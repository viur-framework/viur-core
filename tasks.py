# -*- coding: utf-8 -*-
from datetime import timedelta
from viur.core.update import checkUpdate
from viur.core.config import conf
from viur.core import errors, request, utils
from viur.core import db
from functools import wraps
import json
import logging
import os, sys
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
from typing import Dict, List, Callable
from viur.core.utils import currentRequest, currentSession

_gaeApp = os.environ.get("GAE_APPLICATION")
regionMap = {  # FIXME! Can we even determine the region like this?
	"h": "europe-west3"
}
queueRegion = None
if _gaeApp:
	regionPrefix = _gaeApp.split("~")[0]
	queueRegion = regionMap.get(regionPrefix)

if not queueRegion:
	# Probably local development server
	logging.error("Taskqueue disabled, tasks will run inline!")

taskClient = tasks_v2.CloudTasksClient()

_periodicTasks: Dict[str, Dict[int, Callable]] = {}
_callableTasks = {}
_deferedTasks = {}
_startupTasks = []
_periodicTaskID = 1  # Used to determine bound functions
_appengineServiceIPs = {"10.0.0.1", "0.1.0.1", "0.1.0.2"}


class PermanentTaskFailure(Exception):
	"""Indicates that a task failed, and will never succeed."""
	pass


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
			if not isinstance(v, str) and not callable(v):
				res = self.findBoundTask(task, v, depth + 1)
				if res:
					return (res)
		return (None)

	def deferred(self, *args, **kwargs):
		"""
			This catches one defered call and routes it to its destination
		"""
		global _deferedTasks, _appengineServiceIPs

		req = currentRequest.get().request
		if 'X-AppEngine-TaskName' not in req.headers:
			logging.critical('Detected an attempted XSRF attack. The header "X-AppEngine-Taskname" was not set.')
			raise errors.Forbidden()
		if req.environ.get("HTTP_X_APPENGINE_USER_IP") not in _appengineServiceIPs:
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
				currentSession.get()["user"] = env["user"]
			if "lang" in env and env["lang"]:
				currentRequest.get().language = env["lang"]
			if "transactionMarker" in env:
				marker = db.Get(db.Key("viur-transactionmarker", env["transactionMarker"]))
				if not marker:
					logging.info("Dropping task, transaction %s did not apply" % env["transactionMarker"])
					return
				else:
					logging.info("Executing task, transaction %s did succeed" % env["transactionMarker"])
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

	def cron(self, cronName="default", *args, **kwargs):
		global _callableTasks, _periodicTasks, _appengineServiceIPs
		# logging.debug("Starting maintenance-run")
		# checkUpdate()  # Let the update-module verify the database layout first
		# logging.debug("Updatecheck complete")
		req = currentRequest.get()
		if not req.isDevServer:
			if 'X-Appengine-Cron' not in req.request.headers:
				logging.critical('Detected an attempted XSRF attack. The header "X-AppEngine-Cron" was not set.')
				raise errors.Forbidden()
			if req.request.environ.get("HTTP_X_APPENGINE_USER_IP") not in _appengineServiceIPs:
				logging.critical('Detected an attempted XSRF attack. This request did not originate from Cron.')
				raise errors.Forbidden()
		if cronName not in _periodicTasks:
			logging.warning("Got Cron request '%s' which doesn't have any tasks" % cronName)
		for task, interval in _periodicTasks[cronName].items():  # Call all periodic tasks bound to that queue
			periodicTaskName = "%s_%s" % (cronName, task.periodicTaskName)
			if interval:  # Ensure this task doesn't get called to often
				lastCall = db.Get(db.Key("viur-task-interval", periodicTaskName))
				logging.error("Interval %s" % interval)
				if lastCall and utils.utcNow() - lastCall["date"] < timedelta(minutes=interval):
					logging.debug("Skipping task %s - Has already run recently." % periodicTaskName)
					continue
			res = self.findBoundTask(task)
			try:
				if res:  # Its bound, call it this way :)
					res[0]()
				else:
					task()  # It seems it wasnt bound - call it as a static method
			except Exception as e:
				logging.error("Error calling periodic task %s" % periodicTaskName)
				logging.exception(e)
			else:
				logging.debug("Successfully called task %s" % periodicTaskName)
			if interval:
				# Update its last-call timestamp
				entry = db.Entity(db.Key("viur-task-interval", name=periodicTaskName))
				entry["date"] = utils.utcNow()
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

	cron.exposed = True

	def list(self, *args, **kwargs):
		"""Lists all user-callabe tasks which are callable by this user"""
		global _callableTasks

		class extList(list):
			pass

		res = extList(
			[{"key": x.key, "name": str(x.name), "descr": str(x.descr)} for x in _callableTasks.values() if
			 x().canCall()])
		res.cursor = None
		res.baseSkel = {}
		return (self.render.list(res))

	list.exposed = True

	def execute(self, taskID, *args, **kwargs):
		"""Queues a specific task for the next maintenance run"""
		global _callableTasks
		from viur.core import securitykey
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
		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()
		task.execute(**skel.accessedValues)
		return self.render.addSuccess(skel)

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
		This is a decorator, which always calls the function deferred.
		Unlike Googles implementation, this one works (with bound functions)
	"""
	if "viur_doc_build" in dir(sys):
		return (func)
	__undefinedFlag_ = object()

	def mkDefered(func, self=__undefinedFlag_, *args, **kwargs):
		if not queueRegion:
			# Run tasks inline
			logging.error("Running inline: %s" % func)
			if self is __undefinedFlag_:
				task = lambda: func(*args, **kwargs)
			else:
				task = lambda: func(self, *args, **kwargs)
			req = currentRequest.get()
			if req:
				req.pendingTasks.append(task)  # < This property will be only exist on development server!
			else:
				# Warmup request or something - we have to call it now as we can't deferr it :/
				task()

			return  # Ensure no result gets passed back

		from viur.core.utils import getCurrentUser
		try:
			req = currentRequest.get()
		except:  # This will fail for warmup requests
			req = None
		if req is not None and req.request.headers.get("X-Appengine-Taskretrycount") and not "DEFERED_TASK_CALLED" in dir(req):
			# This is the deferred call
			req.DEFERED_TASK_CALLED = True  # Defer recursive calls to an deferred function again.
			if self is __undefinedFlag_:
				return func(*args, **kwargs)
			else:
				return func(self, *args, **kwargs)
		else:
			try:
				if self.__class__.__name__ == "index":
					funcPath = func.__name__
				else:
					funcPath = "%s/%s" % (self.modulePath, func.__name__)
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
			queue = kwargs.pop("_queue", "default")  # Fixme: Default
			# Try to preserve the important data from the current environment
			env = {"user": None}
			usr = getCurrentUser()
			if usr:
				env["user"] = {"key": usr["key"].id_or_name,
							   "name": usr["name"],
							   "access": usr["access"]}
			try:
				env["lang"] = currentRequest.get().language
			except AttributeError:  # This isn't originating from a normal request
				pass
			if db.IsInTransaction():
				# We have to ensure transaction guarantees for that task also
				env["transactionMarker"] = db.acquireTransactionSuccessMarker()
				# We move that task at least 90 seconds into the future so the transaction has time to settle
				taskargs["countdown"] = max(90, (taskargs.get("countdown") or 0))  # Countdown can be set to None
			if conf["viur.tasks.customEnvironmentHandler"]:
				# Check if this project relies on additional environmental variables and serialize them too
				assert isinstance(conf["viur.tasks.customEnvironmentHandler"], tuple) \
					   and len(conf["viur.tasks.customEnvironmentHandler"]) == 2 \
					   and callable(conf["viur.tasks.customEnvironmentHandler"][0]), \
					"Your customEnvironmentHandler must be a tuple of two callable if set!"
				env["custom"] = conf["viur.tasks.customEnvironmentHandler"][0]()
			pickled = json.dumps((command, (funcPath, args, kwargs, env))).encode("UTF-8")

			project = utils.projectID
			location = queueRegion
			parent = taskClient.queue_path(project, location, queue)
			task = {
				'app_engine_http_request': {  # Specify the type of request.
					'http_method': 'POST',
					'relative_uri': '/_tasks/deferred'
				}
			}
			if taskargs.get("countdown"):
				# We must send a Timestamp Protobuff instead of a date-string
				timestamp = timestamp_pb2.Timestamp()
				timestamp.FromDatetime(utils.utcNow() + timedelta(seconds=taskargs["countdown"]))
				task['schedule_time'] = timestamp
			task['app_engine_http_request']['body'] = pickled

			# Use the client to build and send the task.
			response = taskClient.create_task(parent, task)

			print('Created task {}'.format(response.name))

	global _deferedTasks
	_deferedTasks["%s.%s" % (func.__name__, func.__module__)] = func
	return (lambda *args, **kwargs: mkDefered(func, *args, **kwargs))


def PeriodicTask(interval=0, cronName="default"):
	"""
		Decorator to call a function periodic during maintenance.
		Interval defines a lower bound for the call-frequency for this task;
		it will not be called faster than each interval minutes.
		(Note that the actual delay between two sequent might be much larger)
		:param interval: Call at most every interval minutes. 0 means call as often as possible.
		:type interval: int
	"""

	def mkDecorator(fn):
		global _periodicTasks, _periodicTaskID
		if not cronName in _periodicTasks:
			_periodicTasks[cronName] = {}
		_periodicTasks[cronName][fn] = interval
		fn.periodicTaskID = _periodicTaskID
		fn.periodicTaskName = "%s_%s" % (fn.__module__, fn.__name__)
		_periodicTaskID += 1
		return fn

	return mkDecorator


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


"""
@CallableTask
class DisableApplicationTask(CallableTaskBase):
	" ""
		Allows en- or disabling the application.
	" ""
	key = "viur-disable-server"
	name = translate("server.tasks.DisableApplicationTask.name",
					 defaultText="Enable or disable the application")
	descr = translate("server.tasks.DisableApplicationTask.descr",
					  defaultText="This will enable or disable the application.")
	kindName = "server-task"

	def canCall(self):
		" ""
			Checks wherever the current user can execute this task
			:returns: bool
		" ""
		usr = utils.getCurrentUser()
		return usr and usr["access"] and "root" in usr["access"]

	def dataSkel(self):
		from viur.core.bones import booleanBone, stringBone
		from viur.core.skeleton import Skeleton
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
"""
