import abc
import datetime
import functools
import json
import logging
import os
import sys
import time
import traceback
import typing as t

import grpc
import requests
from google import protobuf
from google.cloud import tasks_v2

from viur.core import current, db, errors, utils
from viur.core.config import conf
from viur.core.decorators import exposed, skey
from viur.core.module import Module

CUSTOM_OBJ = t.TypeVar("CUSTOM_OBJ")  # A JSON serializable object


class CustomEnvironmentHandler(abc.ABC):
    @abc.abstractmethod
    def serialize(self) -> CUSTOM_OBJ:
        """Serialize custom environment data

        This function must not require any parameters and must
        return a JSON serializable object with the desired information.
        """
        ...

    @abc.abstractmethod
    def restore(self, obj: CUSTOM_OBJ) -> None:
        """Restore custom environment data

        This function will receive the object from :meth:`serialize` and should write
        the information it contains to the environment of the deferred request.
        """
        ...


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

if not queueRegion and conf.instance.is_dev_server and os.getenv("TASKS_EMULATOR") is None:
    # Probably local development server
    logging.warning("Taskqueue disabled, tasks will run inline!")

if not conf.instance.is_dev_server or os.getenv("TASKS_EMULATOR") is None:
    taskClient = tasks_v2.CloudTasksClient()
else:
    taskClient = tasks_v2.CloudTasksClient(
        transport=tasks_v2.services.cloud_tasks.transports.CloudTasksGrpcTransport(
            channel=grpc.insecure_channel(os.getenv("TASKS_EMULATOR"))
        )
    )
    queueRegion = "local"

_periodicTasks: dict[str, dict[t.Callable, int]] = {}
_callableTasks = {}
_deferred_tasks = {}
_startupTasks = []
_appengineServiceIPs = {"10.0.0.1", "0.1.0.1", "0.1.0.2"}


class PermanentTaskFailure(Exception):
    """Indicates that a task failed, and will never succeed."""
    pass


def removePeriodicTask(task: t.Callable) -> None:
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
        raise NotImplementedError()


class TaskHandler(Module):
    """
        Task Handler.
        Handles calling of Tasks (queued and periodic), and performs updatechecks
        Do not Modify. Do not Subclass.
    """
    adminInfo = None
    retryCountWarningThreshold = 25

    def findBoundTask(self, task: t.Callable, obj: object, depth: int = 0) -> t.Optional[tuple[t.Callable, object]]:

        """
            Tries to locate the instance, this function belongs to.
            If it succeeds in finding it, it returns the function and its instance (-> its "self").
            Otherwise, None is returned.
            :param task: A callable decorated with @PeriodicTask
            :param obj: Object, which will be scanned in the current iteration.
            :param depth: Current iteration depth.
        """
        if depth > 3 or "periodicTaskName" not in dir(task):  # Limit the maximum amount of recursions
            return None
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

    @exposed
    def queryIter(self, *args, **kwargs):
        """
            This processes one chunk of a queryIter (see below).
        """
        req = current.request.get().request
        self._validate_request()
        data = utils.json.loads(req.body)
        if data["classID"] not in MetaQueryIter._classCache:
            logging.error(f"""Could not continue queryIter - {data["classID"]} not known on this instance""")
        MetaQueryIter._classCache[data["classID"]]._qryStep(data)

    @exposed
    def deferred(self, *args, **kwargs):
        """
            This catches one deferred call and routes it to its destination
        """
        req = current.request.get().request
        self._validate_request()
        # Check if the retry count exceeds our warning threshold
        retryCount = req.headers.get("X-Appengine-Taskretrycount", None)
        if retryCount and int(retryCount) == self.retryCountWarningThreshold:
            from viur.core import email
            email.sendEMailToAdmins(
                "Deferred task retry counter exceeded warning threshold",
                f"""Task {req.headers.get("X-Appengine-Taskname", "")} is retried for the {retryCount}th time."""
            )

        cmd, data = utils.json.loads(req.body)
        funcPath, args, kwargs, env = data
        logging.debug(f"Call task {funcPath} with {cmd=} {args=} {kwargs=} {env=}")

        if env:
            if "user" in env and env["user"]:
                current.session.get()["user"] = env["user"]

                # Load current user into context variable if user module is there.
                if user_mod := getattr(conf.main_app.vi, "user", None):
                    current.user.set(user_mod.getCurrentUser())
            if "lang" in env and env["lang"]:
                current.language.set(env["lang"])
            if "transactionMarker" in env:
                marker = db.Get(db.Key("viur-transactionmarker", env["transactionMarker"]))
                if not marker:
                    logging.info(f"""Dropping task, transaction {env["transactionMarker"]} did not apply""")
                    return
                else:
                    logging.info(f"""Executing task, transaction {env["transactionMarker"]} did succeed""")
            if "custom" in env and conf.tasks_custom_environment_handler:
                # Check if we need to restore additional environmental data
                conf.tasks_custom_environment_handler.restore(env["custom"])
        if cmd == "rel":
            caller = conf.main_app
            pathlist = [x for x in funcPath.split("/") if x]
            for currpath in pathlist:
                if currpath not in dir(caller):
                    logging.error(f"Could not resolve {funcPath=} (failed part was {currpath!r})")
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
            if funcPath not in _deferred_tasks:
                logging.error(f"Missed deferred task {funcPath=} ({args=},{kwargs=})")
            # We call the deferred function *directly* (without walking through the mkDeferred lambda), so ensure
            # that any hit to another deferred function will defer again

            current.request.get().DEFERRED_TASK_CALLED = True
            try:
                _deferred_tasks[funcPath](*args, **kwargs)
            except PermanentTaskFailure:
                logging.error("PermanentTaskFailure")
            except Exception as e:
                logging.exception(e)
                raise errors.RequestTimeout()  # Task-API should retry

    @exposed
    def cron(self, cronName="default", *args, **kwargs):
        req = current.request.get()
        if not conf.instance.is_dev_server:
            self._validate_request(require_cron=True, require_taskname=False)
        if cronName not in _periodicTasks:
            logging.warning(f"Cron request {cronName} doesn't have any tasks")
        # We must defer from cron, as tasks will interpret it as a call originating from task-queue - causing deferred
        # functions to be called directly, wich causes calls with _countdown etc set to fail.
        req.DEFERRED_TASK_CALLED = True
        for task, interval in _periodicTasks[cronName].items():  # Call all periodic tasks bound to that queue
            periodicTaskName = task.periodicTaskName.lower()
            if interval:  # Ensure this task doesn't get called to often
                lastCall = db.Get(db.Key("viur-task-interval", periodicTaskName))
                if lastCall and utils.utcNow() - lastCall["date"] < datetime.timedelta(minutes=interval):
                    logging.debug(f"Task {periodicTaskName!r} has already run recently - skipping.")
                    continue
            res = self.findBoundTask(task, conf.main_app)
            try:
                if res:  # Its bound, call it this way :)
                    res[0]()
                else:
                    task()  # It seems it wasn't bound - call it as a static method
            except Exception as e:
                logging.error(f"Error calling periodic task {periodicTaskName}")
                logging.exception(e)
            else:
                logging.debug(f"Successfully called task {periodicTaskName}")
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

    def _validate_request(
        self,
        *,
        require_cron: bool = False,
        require_taskname: bool = True,
    ) -> None:
        """
        Validate the header and metadata of a request

        If the request is valid, None will be returned.
        Otherwise, an exception will be raised.

        :param require_taskname: Require "X-AppEngine-TaskName" header
        :param require_cron: Require "X-Appengine-Cron" header
        """
        req = current.request.get().request
        if (
            req.environ.get("HTTP_X_APPENGINE_USER_IP") not in _appengineServiceIPs
            and (not conf.instance.is_dev_server or os.getenv("TASKS_EMULATOR") is None)
        ):
            logging.critical("Detected an attempted XSRF attack. This request did not originate from Task Queue.")
            raise errors.Forbidden()
        if require_cron and "X-Appengine-Cron" not in req.headers:
            logging.critical('Detected an attempted XSRF attack. The header "X-AppEngine-Cron" was not set.')
            raise errors.Forbidden()
        if require_taskname and "X-AppEngine-TaskName" not in req.headers:
            logging.critical('Detected an attempted XSRF attack. The header "X-AppEngine-Taskname" was not set.')
            raise errors.Forbidden()

    @exposed
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

    @exposed
    @skey(allow_empty=True)
    def execute(self, taskID, *args, **kwargs):
        """Queues a specific task for the next maintenance run"""
        global _callableTasks
        if taskID in _callableTasks:
            task = _callableTasks[taskID]()
        else:
            return
        if not task.canCall():
            raise errors.Unauthorized()
        skel = task.dataSkel()
        if not kwargs or not skel.fromClient(kwargs) or utils.parse.bool(kwargs.get("bounce")):
            return self.render.add(skel)
        task.execute(**skel.accessedValues)
        return self.render.addSuccess(skel)


TaskHandler.admin = True
TaskHandler.vi = True
TaskHandler.html = True


# Decorators

def retry_n_times(retries: int, email_recipients: None | str | list[str] = None,
                  tpl: None | str = None) -> t.Callable:
    """
    Wrapper for deferred tasks to limit the amount of retries

    :param retries: Number of maximum allowed retries
    :param email_recipients: Email addresses to which a info should be sent
        when the retry limit is reached.
    :param tpl: Instead of the standard text, a custom template can be used.
        The name of an email template must be specified.
    """
    # language=Jinja2
    string_template = \
        """Task {{func_name}} failed {{retries}} times
        This was the last attempt.<br>
        <pre>{{func_module|escape}}.{{func_name|escape}}({{signature|escape}})</pre>
        <pre>{{traceback|escape}}</pre>"""

    def outer_wrapper(func):
        @functools.wraps(func)
        def inner_wrapper(*args, **kwargs):
            try:
                retry_count = int(current.request.get().request.headers.get("X-Appengine-Taskretrycount", -1))
            except AttributeError:
                # During warmup current.request is None (at least on local devserver)
                retry_count = -1
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                logging.exception(f"Task {func.__qualname__} failed: {exc}")
                logging.info(
                    f"This was the {retry_count}. retry."
                    f"{retries - retry_count} retries remaining. (total = {retries})"
                )
                if retry_count < retries:
                    # Raise the exception to mark this task as failed, so the task queue can retry it.
                    raise exc
                else:
                    if email_recipients:
                        args_repr = [repr(arg) for arg in args]
                        kwargs_repr = [f"{k!s}={v!r}" for k, v in kwargs.items()]
                        signature = ", ".join(args_repr + kwargs_repr)
                        try:
                            from viur.core import email
                            email.sendEMail(
                                dests=email_recipients,
                                tpl=tpl,
                                stringTemplate=string_template if tpl is None else string_template,
                                # The following params provide information for the emails templates
                                func_name=func.__name__,
                                func_qualname=func.__qualname__,
                                func_module=func.__module__,
                                retries=retries,
                                args=args,
                                kwargs=kwargs,
                                signature=signature,
                                traceback=traceback.format_exc(),
                            )
                        except Exception:
                            logging.exception("Failed to send email to %r", email_recipients)
                    # Mark as permanently failed (could return nothing too)
                    raise PermanentTaskFailure()

        return inner_wrapper

    return outer_wrapper


def noRetry(f):
    """Prevents a deferred Function from being called a second time"""
    logging.warning("Use of `@noRetry` is deprecated; Use `@retry_n_times(0)` instead!", stacklevel=2)
    return retry_n_times(0)(f)


def CallDeferred(func: t.Callable) -> t.Callable:
    """
    This is a decorator, which always calls the wrapped method deferred.

    The call will be packed and queued into a Cloud Tasks queue.
    The Task Queue calls the TaskHandler which executed the wrapped function
    with the originally arguments in a different request.


    In addition to the arguments for the wrapped methods you can set these:

    _queue: Specify the queue in which the task should be pushed.
        "default" is the default value. The queue must exist (use the queue.yaml).

    _countdown: Specify a time in seconds after which the task should be called.
        This time is relative to the moment where the wrapped method has been called.

    _eta: Instead of a relative _countdown value you can specify a `datetime`
         when the task is scheduled to be attempted or retried.

    _name: Specify a custom name for the cloud task. Must be unique and can
        contain only letters ([A-Za-z]), numbers ([0-9]), hyphens (-), colons (:), or periods (.).

    _target_version: Specify a version on which to run this task.
        By default, a task will be run on the same version where the wrapped method has been called.

    _call_deferred: Calls the @CallDeferred decorated method directly.
        This is for example necessary, to call a super method which is decorated with @CallDeferred.

    ..  code-block:: python

        # Example for use of the _call_deferred-parameter
        class A(Module):
            @CallDeferred
            def task(self):
                ...

        class B(A):
            @CallDeferred
            def task(self):
                super().task(_call_deferred=False)  # avoid secondary deferred call
                ...

    See also:
        https://cloud.google.com/python/docs/reference/cloudtasks/latest/google.cloud.tasks_v2.types.Task
        https://cloud.google.com/python/docs/reference/cloudtasks/latest/google.cloud.tasks_v2.types.CreateTaskRequest
    """
    if "viur_doc_build" in dir(sys):
        return func

    __undefinedFlag_ = object()

    def make_deferred(func, self=__undefinedFlag_, *args, **kwargs):
        # Extract possibly provided task flags from kwargs
        queue = kwargs.pop("_queue", "default")
        call_deferred = kwargs.pop("_call_deferred", True)
        target_version = kwargs.pop("_target_version", conf.instance.app_version)
        if "_eta" in kwargs and "_countdown" in kwargs:
            raise ValueError("You cannot set the _countdown and _eta argument together!")
        taskargs = {k: kwargs.pop(f"_{k}", None) for k in ("countdown", "eta", "name")}

        logging.debug(
            f"make_deferred {func=}, {self=}, {args=}, {kwargs=}, "
            f"{queue=}, {call_deferred=}, {target_version=}, {taskargs=}"
        )

        try:
            req = current.request.get()
        except:  # This will fail for warmup requests
            req = None

        if not queueRegion:
            # Run tasks inline
            logging.debug(f"{func=} will be executed inline")

            @functools.wraps(func)
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

        # It's the deferred method which is called from the task queue, this has to be called directly
        call_deferred &= not (req and req.request.headers.get("X-Appengine-Taskretrycount")
                              and "DEFERRED_TASK_CALLED" not in dir(req))

        if not call_deferred:
            if self is __undefinedFlag_:
                return func(*args, **kwargs)

            req.DEFERRED_TASK_CALLED = True
            return func(self, *args, **kwargs)

        else:
            try:
                if self.__class__.__name__ == "index":
                    funcPath = func.__name__
                else:
                    funcPath = f"{self.modulePath}/{func.__name__}"

                command = "rel"

            except:
                funcPath = f"{func.__name__}.{func.__module__}"

                if self is not __undefinedFlag_:
                    args = (self,) + args  # Re-append self to args, as this function is (hopefully) unbound

                command = "unb"

            taskargs["url"] = "/_tasks/deferred"
            taskargs["headers"] = {"Content-Type": "application/octet-stream"}

            # Try to preserve the important data from the current environment
            try:  # We might get called inside a warmup request without session
                usr = current.session.get().get("user")
                if "password" in usr:
                    del usr["password"]

            except:
                usr = None

            env = {"user": usr}

            try:
                env["lang"] = current.language.get()
            except AttributeError:  # This isn't originating from a normal request
                pass

            if db.IsInTransaction():
                # We have to ensure transaction guarantees for that task also
                env["transactionMarker"] = db.acquireTransactionSuccessMarker()
                # We move that task at least 90 seconds into the future so the transaction has time to settle
                taskargs["countdown"] = max(90, taskargs.get("countdown") or 0)  # Countdown can be set to None

            if conf.tasks_custom_environment_handler:
                # Check if this project relies on additional environmental variables and serialize them too
                env["custom"] = conf.tasks_custom_environment_handler.serialize()

            # Create task description
            task = tasks_v2.Task(
                app_engine_http_request=tasks_v2.AppEngineHttpRequest(
                    body=utils.json.dumps((command, (funcPath, args, kwargs, env))).encode(),
                    http_method=tasks_v2.HttpMethod.POST,
                    relative_uri=taskargs["url"],
                    app_engine_routing=tasks_v2.AppEngineRouting(
                        version=target_version,
                    ),
                ),
            )
            if taskargs.get("name"):
                task.name = taskClient.task_path(conf.instance.project_id, queueRegion, queue, taskargs["name"])

            # Set a schedule time in case eta (absolut) or countdown (relative) was set.
            eta = taskargs.get("eta")
            if seconds := taskargs.get("countdown"):
                eta = utils.utcNow() + datetime.timedelta(seconds=seconds)
            if eta:
                # We must send a Timestamp Protobuf instead of a date-string
                timestamp = protobuf.timestamp_pb2.Timestamp()
                timestamp.FromDatetime(eta)
                task.schedule_time = timestamp

            # Use the client to build and send the task.
            parent = taskClient.queue_path(conf.instance.project_id, queueRegion, queue)
            logging.debug(f"{parent=}, {task=}")
            taskClient.create_task(tasks_v2.CreateTaskRequest(parent=parent, task=task))

            logging.info(f"Created task {func.__name__}.{func.__module__} with {args=} {kwargs=} {env=}")

    global _deferred_tasks
    _deferred_tasks[f"{func.__name__}.{func.__module__}"] = func

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return make_deferred(func, *args, **kwargs)

    return wrapper


def callDeferred(func):
    """
    Deprecated version of CallDeferred
    """
    import logging, warnings

    msg = "Use of @callDeferred is deprecated, use @CallDeferred instead."
    logging.warning(msg, stacklevel=3)
    warnings.warn(msg, stacklevel=3)

    return CallDeferred(func)


def PeriodicTask(interval: int = 0, cronName: str = "default") -> t.Callable:
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
        if cronName not in _periodicTasks:
            _periodicTasks[cronName] = {}
        _periodicTasks[cronName][fn] = interval
        fn.periodicTaskName = f"{fn.__module__}_{fn.__qualname__}".replace(".", "_").lower()
        return fn

    return mkDecorator


def CallableTask(fn: t.Callable) -> t.Callable:
    """Marks a Class as representing a user-callable Task.
    It *should* extend CallableTaskBase and *must* provide
    its API
    """
    global _callableTasks
    _callableTasks[fn.key] = fn
    return fn


def StartupTask(fn: t.Callable) -> t.Callable:
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
    def startIterOnQuery(cls, query: db.Query, customData: t.Any = None) -> None:
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
    def _requeueStep(cls, qryDict: dict[str, t.Any]) -> None:
        """
            Internal use only. Pushes a new step defined in qryDict to either the taskqueue or append it to
            the current request    if we are on the local development server.
        """
        if not queueRegion:  # Run tasks inline - hopefully development server
            req = current.request.get()
            task = lambda *args, **kwargs: cls._qryStep(qryDict)
            if req:
                req.pendingTasks.append(task)  # < This property will be only exist on development server!
                return
        taskClient.create_task(tasks_v2.CreateTaskRequest(
            parent=taskClient.queue_path(conf.instance.project_id, queueRegion, cls.queueName),
            task=tasks_v2.Task(
                app_engine_http_request=tasks_v2.AppEngineHttpRequest(
                    body=utils.json.dumps(qryDict).encode(),
                    http_method=tasks_v2.HttpMethod.POST,
                    relative_uri="/_tasks/queryIter",
                    app_engine_routing=tasks_v2.AppEngineRouting(
                        version=conf.instance.app_version,
                    ),
                )
            ),
        ))

    @classmethod
    def _qryStep(cls, qryDict: dict[str, t.Any]) -> None:
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
                time.sleep(5)
                try:
                    cls.handleEntry(item, qryDict["customData"])
                except Exception as e:  # Second exception - call error_handler
                    try:
                        doCont = cls.handleError(item, qryDict["customData"], e)
                    except Exception as e:
                        logging.error(f"handleError failed on {item} - bailing out")
                        logging.exception(e)
                        doCont = False
                    if not doCont:
                        logging.error(f"Exiting queryIter on cursor {qry.getCursor()!r}")
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
        logging.debug(f"handleEntry called on {cls} with {entry}.")

    @classmethod
    def handleFinish(cls, totalCount: int, customData):
        """
            Overridable hook that indicates the current run has been finished.
        """
        logging.debug(f"handleFinish called on {cls} with {totalCount} total Entries processed")

    @classmethod
    def handleError(cls, entry, customData, exception) -> bool:
        """
            Handle a error occurred in handleEntry.
            If this function returns True, the queryIter continues, otherwise it breaks and prints the current cursor.
        """
        logging.debug(f"handleError called on {cls} with {entry}.")
        logging.exception(exception)
        return True


class DeleteEntitiesIter(QueryIter):
    """
    Simple Query-Iter to delete all entities encountered.

    ..Warning: When iterating over skeletons, make sure that the
        query was created using `Skeleton().all()`.
        This way the `Skeleton.delete()` method can be used and
        the appropriate post-processing can be done.
    """

    @classmethod
    def handleEntry(cls, entry, customData):
        from viur.core.skeleton import SkeletonInstance
        if isinstance(entry, SkeletonInstance):
            entry.delete()
        else:
            db.Delete(entry.key)
