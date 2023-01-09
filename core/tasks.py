import base64
import grpc
import json
import logging
import os
import pytz
import sys
import requests
from datetime import datetime, timedelta
from functools import wraps
from google.cloud import tasks_v2
from google.cloud.tasks_v2.services.cloud_tasks.transports import CloudTasksGrpcTransport
from google.protobuf import timestamp_pb2
from time import sleep
from typing import Any, Callable, Dict, Optional, Tuple

from viur.core import db, errors, utils
from viur.core.config import conf
from viur.core.utils import currentLanguage, currentRequest, currentSession


# class JsonKeyEncoder(json.JSONEncoder):
def preprocessJsonObject(o):
    """
        Add support for Keys, Datetime, Bytes and db.Entities in deferred tasks.
        This is not a subclass of json.JSONEncoder anymore, as db.Entites are a subclass of dict, which
        is always handled from the json module itself.
    """
    if isinstance(o, db.Key):
        return {".__key__": db.encodeKey(o)}
    elif isinstance(o, datetime):
        return {".__datetime__": o.astimezone(pytz.UTC).strftime("%d.%m.%Y %H:%M:%S")}
    elif isinstance(o, bytes):
        return {".__bytes__": base64.b64encode(o).decode("ASCII")}
    elif isinstance(o, db.Entity):
        return {".__entity__": preprocessJsonObject(dict(o)), ".__ekey__": db.encodeKey(o.key) if o.key else None}
    elif isinstance(o, dict):
        return {preprocessJsonObject(k): preprocessJsonObject(v) for k, v in o.items()}
    elif isinstance(o, (list, tuple, set)):
        return [preprocessJsonObject(x) for x in o]
    else:
        return o


def jsonDecodeObjectHook(obj):
    """
        Inverse to JsonKeyEncoder: Check if the object matches a custom ViUR type and recreate it accordingly
    """
    if len(obj) == 1:
        if ".__key__" in obj:
            return db.Key.from_legacy_urlsafe(obj[".__key__"])
        elif ".__datetime__" in obj:
            value = datetime.strptime(obj[".__datetime__"], "%d.%m.%Y %H:%M:%S")
            return datetime(value.year, value.month, value.day, value.hour, value.minute, value.second, tzinfo=pytz.UTC)
        elif ".__bytes__" in obj:
            return base64.b64decode(obj[".__bytes__"])
    elif len(obj) == 2 and ".__entity__" in obj and ".__ekey__" in obj:
        r = db.Entity(db.Key.from_legacy_urlsafe(obj[".__ekey__"]) if obj[".__ekey__"] else None)
        r.update(obj[".__entity__"])
        return r
    return obj


_gaeApp = os.environ.get("GAE_APPLICATION")

queueRegion = None
if _gaeApp:

    try:
        headers = {"Metadata-Flavor": "Google"}
        r = requests.get("http://metadata.google.internal/computeMetadata/v1/instance/region", headers=headers)
        # r.text should be look like this "projects/(project-number)/region/(region)"
        # like so "projects/1234567890/region/europe-west3"
        queueRegion = r.text.split("/")[-1]
    except Exception as e:  # Something went wrong with the Google Metadata Sever we use the old way
        logging.warning(f"Can't obtain queueRegion from Google MetaData Server due exception {e=}")
        regionPrefix = _gaeApp.split("~")[0]
        regionMap = {
            "h": "europe-west3",
            "e": "europe-west1"
        }
        queueRegion = regionMap.get(regionPrefix)

if not queueRegion and conf["viur.instance.is_dev_server"] and os.getenv("TASKS_EMULATOR") is None:
    # Probably local development server
    logging.warning("Taskqueue disabled, tasks will run inline!")

if not conf["viur.instance.is_dev_server"] or os.getenv("TASKS_EMULATOR") is None:
    taskClient = tasks_v2.CloudTasksClient()
else:
    taskClient = tasks_v2.CloudTasksClient(
        transport=CloudTasksGrpcTransport(channel=grpc.insecure_channel(os.getenv("TASKS_EMULATOR")))
    )
    queueRegion = "local"

_periodicTasks: Dict[str, Dict[Callable, int]] = {}
_callableTasks = {}
_deferred_tasks = {}
_startupTasks = []
_appengineServiceIPs = {"10.0.0.1", "0.1.0.1", "0.1.0.2"}


class PermanentTaskFailure(Exception):
    """Indicates that a task failed, and will never succeed."""
    pass


def removePeriodicTask(task: Callable) -> None:
    """
    Removes a periodic task from the queue. Useful to unqueue an task
    that has been inherited from an overridden module.
    """
    global _periodicTasks
    assert "periodicTaskName" in dir(task), "This is not a periodic task? "
    for queueDict in _periodicTasks.values():
        if task in queueDict:
            del queueDict[task]


class CallableTaskBase:
    """
        Base class for user-callable tasks.
        Must be subclassed.
    """
    key = None  # Unique identifier for this task
    name = None  # Human-Readable name
    descr = None  # Human-Readable description
    kindName = "server-task"

    def canCall(self) -> bool:
        """
            Checks wherever the current user can execute this task
            :returns: bool
        """
        return False

    def dataSkel(self):
        """
            If additional data is needed, return a skeleton-instance here.
            These values are then passed to *execute*.
        """
        return None

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

    def findBoundTask(self, task: Callable, obj: object = None, depth: int = 0) -> Optional[Tuple[Callable, object]]:
        """
            Tries to locate the instance, this function belongs to.
            If it succeeds in finding it, it returns the function and its instance (-> its "self").
            Otherwise, None is returned.
            :param task: A callable decorated with @PeriodicTask
            :param obj: Object, which will be scanned in the current iteration. None means start at conf["viur.mainApp"].
            :param depth: Current iteration depth.
        """
        if depth > 3 or not "periodicTaskName" in dir(task):  # Limit the maximum amount of recursions
            return None
        obj = obj or conf["viur.mainApp"]
        for attr in dir(obj):
            if attr.startswith("_"):
                continue
            try:
                v = getattr(obj, attr)
            except AttributeError:
                continue
            if callable(v) and "periodicTaskName" in dir(v) and str(v.periodicTaskName) == str(task.periodicTaskName):
                return v, obj
            if not isinstance(v, str) and not callable(v):
                res = self.findBoundTask(task, v, depth + 1)
                if res:
                    return res
        return None

    def queryIter(self, *args, **kwargs):
        """
            This processes one chunk of a queryIter (see below).
        """
        global _deferred_tasks, _appengineServiceIPs
        req = currentRequest.get().request
        if 'X-AppEngine-TaskName' not in req.headers:
            logging.critical('Detected an attempted XSRF attack. The header "X-AppEngine-Taskname" was not set.')
            raise errors.Forbidden()
        if req.environ.get("HTTP_X_APPENGINE_USER_IP") not in _appengineServiceIPs:
            logging.critical('Detected an attempted XSRF attack. This request did not originate from Task Queue.')
            raise errors.Forbidden()
        data = json.loads(req.body, object_hook=jsonDecodeObjectHook)
        if data["classID"] not in MetaQueryIter._classCache:
            logging.error("Could not continue queryIter - %s not known on this instance" % data["classID"])
        MetaQueryIter._classCache[data["classID"]]._qryStep(data)

    queryIter.exposed = True

    def deferred(self, *args, **kwargs):
        """
            This catches one deferred call and routes it to its destination
        """
        global _deferred_tasks, _appengineServiceIPs
        req = currentRequest.get().request
        if 'X-AppEngine-TaskName' not in req.headers:
            logging.critical('Detected an attempted XSRF attack. The header "X-AppEngine-Taskname" was not set.')
            raise errors.Forbidden()
        if req.environ.get("HTTP_X_APPENGINE_USER_IP") not in _appengineServiceIPs:
            if not conf["viur.instance.is_dev_server"] or os.getenv("TASKS_EMULATOR") is None:
                logging.critical('Detected an attempted XSRF attack. This request did not originate from Task Queue.')
            raise errors.Forbidden()
        # Check if the retry count exceeds our warning threshold
        retryCount = req.headers.get("X-Appengine-Taskretrycount", None)
        if retryCount:
            if int(retryCount) == self.retryCountWarningThreshold:
                from viur.core import email
                email.sendEMailToAdmins("Deferred task retry count exceeded warning threshold",
                                        "Task %s will now be retried for the %sth time." % (
                                            req.headers.get("X-Appengine-Taskname", ""),
                                            retryCount))
        cmd, data = json.loads(req.body, object_hook=jsonDecodeObjectHook)
        funcPath, args, kwargs, env = data
        logging.debug(f"Call task {funcPath} with {cmd=} {args=} {kwargs=} {env=}")

        if env:
            if "user" in env and env["user"]:
                currentSession.get()["user"] = env["user"]
            if "lang" in env and env["lang"]:
                currentLanguage.set(env["lang"])
            if "transactionMarker" in env:
                marker = db.Get(db.Key("viur-transactionmarker", env["transactionMarker"]))
                if not marker:
                    logging.info("Dropping task, transaction %s did not apply" % env["transactionMarker"])
                    return
                else:
                    logging.info("Executing task, transaction %s did succeed" % env["transactionMarker"])
            if "custom" in env and conf["viur.tasks.customEnvironmentHandler"]:
                # Check if we need to restore additional environmental data
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
                    logging.error("ViUR missed a deferred task! Could not resolve the path %s. "
                                  "Failed segment was %s", funcPath, currpath)
                    return
                caller = getattr(caller, currpath)
            try:
                caller(*args, **kwargs)
            except PermanentTaskFailure:
                logging.error("PermanentTaskFailure")
            except Exception as e:
                logging.exception(e)
                raise errors.RequestTimeout()  # Task-API should retry
        elif cmd == "unb":
            if not funcPath in _deferred_tasks:
                logging.error("ViUR missed a deferred task! %s(%s,%s)", funcPath, args, kwargs)
            # We call the deferred function *directly* (without walking through the mkDeferred lambda), so ensure
            # that any hit to another deferred function will defer again

            currentRequest.get().DEFERRED_TASK_CALLED = True
            try:
                _deferred_tasks[funcPath](*args, **kwargs)
            except PermanentTaskFailure:
                logging.error("PermanentTaskFailure")
            except Exception as e:
                logging.exception(e)
                raise errors.RequestTimeout()  # Task-API should retry

    deferred.exposed = True

    def cron(self, cronName="default", *args, **kwargs):
        global _callableTasks, _periodicTasks, _appengineServiceIPs
        req = currentRequest.get()
        if not conf["viur.instance.is_dev_server"]:
            if 'X-Appengine-Cron' not in req.request.headers:
                logging.critical('Detected an attempted XSRF attack. The header "X-AppEngine-Cron" was not set.')
                raise errors.Forbidden()
            if req.request.environ.get("HTTP_X_APPENGINE_USER_IP") not in _appengineServiceIPs:
                logging.critical('Detected an attempted XSRF attack. This request did not originate from Cron.')
                raise errors.Forbidden()
        if cronName not in _periodicTasks:
            logging.warning("Got Cron request '%s' which doesn't have any tasks" % cronName)
        # We must defer from cron, as tasks will interpret it as a call originating from task-queue - causing deferred
        # functions to be called directly, wich causes calls with _countdown etc set to fail.
        req.DEFERRED_TASK_CALLED = True
        for task, interval in _periodicTasks[cronName].items():  # Call all periodic tasks bound to that queue
            periodicTaskName = task.periodicTaskName.lower()
            if interval:  # Ensure this task doesn't get called to often
                lastCall = db.Get(db.Key("viur-task-interval", periodicTaskName))
                if lastCall and utils.utcNow() - lastCall["date"] < timedelta(minutes=interval):
                    logging.debug("Skipping task %s - Has already run recently." % periodicTaskName)
                    continue
            res = self.findBoundTask(task)
            try:
                if res:  # Its bound, call it this way :)
                    res[0]()
                else:
                    task()  # It seems it wasn't bound - call it as a static method
            except Exception as e:
                logging.error("Error calling periodic task %s", periodicTaskName)
                logging.exception(e)
            else:
                logging.debug("Successfully called task %s", periodicTaskName)
            if interval:
                # Update its last-call timestamp
                entry = db.Entity(db.Key("viur-task-interval", periodicTaskName))
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
        """Lists all user-callable tasks which are callable by this user"""
        global _callableTasks

        tasks = db.SkelListRef()
        tasks.extend([{
            "key": x.key,
            "name": str(x.name),
            "descr": str(x.descr)
        } for x in _callableTasks.values() if x().canCall()
        ])

        return self.render.list(tasks)

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
        skey = kwargs.get("skey", "")
        if len(kwargs) == 0 or not skel.fromClient(kwargs) or kwargs.get("bounce") == "1":
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
    """Prevents a deferred Function from being called a second time"""

    @wraps(f)
    def wrappedFunc(*args, **kwargs):
        try:
            f(*args, **kwargs)
        except Exception as e:
            logging.exception(e)
            raise PermanentTaskFailure()

    return wrappedFunc


def CallDeferred(func):
    """
        This is a decorator, which always calls the function deferred.
        Unlike Googles implementation, this one works (with bound functions)
    """
    if "viur_doc_build" in dir(sys):
        return func

    __undefinedFlag_ = object()

    def make_deferred(func, self=__undefinedFlag_, *args, **kwargs):
        # Extract possibly provided task flags from kwargs
        queue = kwargs.pop("_queue", "default")
        taskargs = {k: kwargs.pop(f"_{k}", None) for k in ("countdown", "eta", "name", "target", "retry_options")}

        logging.debug(f"make_deferred {func=}, {self=}, {args=}, {kwargs=}, {queue=}, {taskargs=}")

        try:
            req = currentRequest.get()
        except:  # This will fail for warmup requests
            req = None

        if not queueRegion:
            # Run tasks inline
            logging.debug(f"{func=} will be executed inline")
            @wraps(func)
            def task():
                if self is __undefinedFlag_:
                    return func(*args, **kwargs)
                else:
                    return func(self, *args, **kwargs)

            if req:
                req.pendingTasks.append(task)  # This property only exists on development server!
            else:
                # Warmup request or something - we have to call it now as we can't defer it :/
                task()

            return  # Ensure no result gets passed back

        if req and req.request.headers.get("X-Appengine-Taskretrycount") and "DEFERRED_TASK_CALLED" not in dir(req):
            if self is __undefinedFlag_:
                return func(*args, **kwargs)

            req.DEFERRED_TASK_CALLED = True
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

                if self is not __undefinedFlag_:
                    args = (self,) + args  # Re-append self to args, as this function is (hopefully) unbound

                command = "unb"

            taskargs["url"] = "/_tasks/deferred"
            taskargs["headers"] = {"Content-Type": "application/octet-stream"}

            # Try to preserve the important data from the current environment
            try:  # We might get called inside a warmup request without session
                usr = currentSession.get().get("user")
                if "password" in usr:
                    del usr["password"]

            except:
                usr = None

            env = {"user": usr}

            try:
                env["lang"] = currentLanguage.get()
            except AttributeError:  # This isn't originating from a normal request
                pass

            if db.IsInTransaction():
                # We have to ensure transaction guarantees for that task also
                env["transactionMarker"] = db.acquireTransactionSuccessMarker()
                # We move that task at least 90 seconds into the future so the transaction has time to settle
                taskargs["countdown"] = max(90, taskargs.get("countdown") or 0)  # Countdown can be set to None

            if conf["viur.tasks.customEnvironmentHandler"]:
                # Check if this project relies on additional environmental variables and serialize them too
                assert isinstance(conf["viur.tasks.customEnvironmentHandler"], tuple) \
                       and len(conf["viur.tasks.customEnvironmentHandler"]) == 2 \
                       and callable(conf["viur.tasks.customEnvironmentHandler"][0]), \
                    "Your customEnvironmentHandler must be a tuple of two callable if set!"
                env["custom"] = conf["viur.tasks.customEnvironmentHandler"][0]()

            # Create task description
            task = {
                "app_engine_http_request": {  # Specify the type of request.
                    "body": json.dumps(preprocessJsonObject((command, (funcPath, args, kwargs, env)))).encode("UTF-8"),
                    "http_method": tasks_v2.HttpMethod.POST,
                    "relative_uri": taskargs["url"]
                }
            }

            # Set a schedule time in case countdown was set.
            if seconds := taskargs.get("countdown"):
                # We must send a Timestamp Protobuf instead of a date-string
                timestamp = timestamp_pb2.Timestamp()
                timestamp.FromDatetime(utils.utcNow() + timedelta(seconds=seconds))
                task["schedule_time"] = timestamp

            # Use the client to build and send the task.
            parent = taskClient.queue_path(conf["viur.instance.project_id"], queueRegion, queue)
            logging.debug(f"{parent=}, {task=}")
            taskClient.create_task(parent=parent, task=task)

            logging.info(f"Created task {func.__name__}.{func.__module__} with {args=} {kwargs=} {env=}")

    global _deferred_tasks
    _deferred_tasks["%s.%s" % (func.__name__, func.__module__)] = func

    @wraps(func)
    def wrapper(*args, **kwargs):
        return make_deferred(func, *args, **kwargs)

    return wrapper


def callDeferred(func):
    """
    Deprecated version of CallDeferred
    """
    import logging, warnings

    msg = f"Use of @callDeferred is deprecated, use @CallDeferred instead."
    logging.warning(msg, stacklevel=3)
    warnings.warn(msg, stacklevel=3)

    return CallDeferred(func)


def PeriodicTask(interval: int = 0, cronName: str = "default") -> Callable:
    """
        Decorator to call a function periodic during maintenance.
        Interval defines a lower bound for the call-frequency for this task;
        it will not be called faster than each interval minutes.
        (Note that the actual delay between two sequent might be much larger)

        :param interval: Call at most every interval minutes. 0 means call as often as possible.
    """

    def mkDecorator(fn):
        global _periodicTasks
        if fn.__name__.startswith("_"):
            raise RuntimeError("Periodic called methods cannot start with an underscore! "
                               f"Please rename {fn.__name__!r}")
        if not cronName in _periodicTasks:
            _periodicTasks[cronName] = {}
        _periodicTasks[cronName][fn] = interval
        fn.periodicTaskName = ("%s_%s" % (fn.__module__, fn.__qualname__)).replace(".", "_").lower()
        return fn

    return mkDecorator


def CallableTask(fn: Callable) -> Callable:
    """Marks a Class as representing a user-callable Task.
    It *should* extend CallableTaskBase and *must* provide
    its API
    """
    global _callableTasks
    _callableTasks[fn.key] = fn
    return fn


def StartupTask(fn: Callable) -> Callable:
    """
        Functions decorated with this are called shortly at instance startup.
        It's *not* guaranteed that they actually run on the instance that just started up!
        Wrapped functions must not take any arguments.
    """
    global _startupTasks
    _startupTasks.append(fn)
    return fn


@CallDeferred
def runStartupTasks():
    """
        Runs all queued startupTasks.
        Do not call directly!
    """
    global _startupTasks
    for st in _startupTasks:
        st()


class MetaQueryIter(type):
    """
        This is the meta class for QueryIters.
        Used only to keep track of all subclasses of QueryIter so we can emit the callbacks
        on the correct class.
    """
    _classCache = {}  # Mapping className -> Class

    def __init__(cls, name, bases, dct):
        MetaQueryIter._classCache[str(cls)] = cls
        cls.__classID__ = str(cls)
        super(MetaQueryIter, cls).__init__(name, bases, dct)


class QueryIter(object, metaclass=MetaQueryIter):
    """
        BaseClass to run a database Query and process each entry matched.
        This will run each step deferred, so it is possible to process an arbitrary number of entries
        without being limited by time or memory.

        To use this class create a subclass, override the classmethods handleEntry and handleFinish and then
        call startIterOnQuery with an instance of a database Query (and possible some custom data to pass along)
    """
    queueName = "default"  # Name of the taskqueue we will run on

    @classmethod
    def startIterOnQuery(cls, query: db.Query, customData: Any = None) -> None:
        """
            Starts iterating the given query on this class. Will return immediately, the first batch will already
            run deferred.

            Warning: Any custom data *must* be json-serializable and *must* be passed in customData. You cannot store
            any data on this class as each chunk may run on a different instance!
        """
        assert not (query._customMultiQueryMerge or query._calculateInternalMultiQueryLimit), \
            "Cannot iter a query with postprocessing"
        assert isinstance(query.queries, db.QueryDefinition), "Unsatisfiable query or query with an IN filter"
        qryDict = {
            "kind": query.kind,
            "srcSkel": query.srcSkel.kindName if query.srcSkel else None,
            "filters": query.queries.filters,
            "orders": [(propName, sortOrder.value) for propName, sortOrder in query.queries.orders],
            "startCursor": query.queries.startCursor,
            "endCursor": query.queries.endCursor,
            "origKind": query.origKind,
            "distinct": query.queries.distinct,
            "classID": cls.__classID__,
            "customData": customData,
            "totalCount": 0
        }
        cls._requeueStep(qryDict)

    @classmethod
    def _requeueStep(cls, qryDict: Dict[str, Any]) -> None:
        """
            Internal use only. Pushes a new step defined in qryDict to either the taskqueue or append it to
            the current request    if we are on the local development server.
        """
        if not queueRegion:  # Run tasks inline - hopefully development server
            req = currentRequest.get()
            task = lambda *args, **kwargs: cls._qryStep(qryDict)
            if req:
                req.pendingTasks.append(task)  # < This property will be only exist on development server!
                return
        project = conf["viur.instance.project_id"]
        location = queueRegion
        parent = taskClient.queue_path(project, location, cls.queueName)
        task = {
            'app_engine_http_request': {  # Specify the type of request.
                'http_method': 'POST',
                'relative_uri': '/_tasks/queryIter'
            }
        }
        task['app_engine_http_request']['body'] = json.dumps(preprocessJsonObject(qryDict)).encode("UTF-8")
        taskClient.create_task(parent=parent, task=task)

    @classmethod
    def _qryStep(cls, qryDict: Dict[str, Any]) -> None:
        """
            Internal use only. Processes one block of five entries from the query defined in qryDict and
            reschedules the next block.
        """
        from viur.core.skeleton import skeletonByKind
        qry = db.Query(qryDict["kind"])
        qry.srcSkel = skeletonByKind(qryDict["srcSkel"])() if qryDict["srcSkel"] else None
        qry.queries.filters = qryDict["filters"]
        qry.queries.orders = [(propName, db.SortOrder(sortOrder)) for propName, sortOrder in qryDict["orders"]]
        qry.setCursor(qryDict["startCursor"], qryDict["endCursor"])
        qry.origKind = qryDict["origKind"]
        qry.queries.distinct = qryDict["distinct"]
        if qry.srcSkel:
            qryIter = qry.fetch(5)
        else:
            qryIter = qry.run(5)
        for item in qryIter:
            try:
                cls.handleEntry(item, qryDict["customData"])
            except:  # First exception - we'll try another time (probably/hopefully transaction collision)
                sleep(5)
                try:
                    cls.handleEntry(item, qryDict["customData"])
                except Exception as e:  # Second exception - call errorHandler
                    try:
                        doCont = cls.handleError(item, qryDict["customData"], e)
                    except Exception as e:
                        logging.error("handleError failed on %s - bailing out" % item)
                        logging.exception(e)
                        doCont = False
                    if not doCont:
                        logging.error("Exiting queryItor on cursor %s" % qry.getCursor())
                        return
            qryDict["totalCount"] += 1
        cursor = qry.getCursor()
        if cursor:
            qryDict["startCursor"] = cursor
            cls._requeueStep(qryDict)
        else:
            cls.handleFinish(qryDict["totalCount"], qryDict["customData"])

    @classmethod
    def handleEntry(cls, entry, customData):
        """
            Overridable hook to process one entry. "entry" will be either an db.Entity or an
            SkeletonInstance (if that query has been created by skel.all())

            Warning: If your query has an sortOrder other than __key__ and you modify that property here
            it is possible to encounter that object later one *again* (as it may jump behind the current cursor).
        """
        logging.debug("handleEntry called on %s with %s." % (cls, entry))

    @classmethod
    def handleFinish(cls, totalCount: int, customData):
        """
            Overridable hook that indicates the current run has been finished.
        """
        logging.debug("handleFinish called on %s with %s total Entries processed" % (cls, totalCount))

    @classmethod
    def handleError(cls, entry, customData, exception) -> bool:
        """
            Handle a error occurred in handleEntry.
            If this function returns True, the queryIter continues, otherwise it breaks and prints the current cursor.
        """
        logging.debug("handleError called on %s with %s." % (cls, entry))
        logging.exception(exception)
        return True


class DeleteEntitiesIter(QueryIter):
    """
        Simple Query-Iter to delete all entities encountered.

        ..Warning: Do not use this iter on skeletons. It only works on the low-level db API and would not clear
            relations, locks etc.
    """

    @classmethod
    def handleEntry(cls, entry, customData):
        db.Delete(entry.key)
