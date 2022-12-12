import logging
import google.cloud.logging
from google.cloud.logging import Resource
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud.logging_v2.handlers.handlers import EXCLUDED_LOGGER_DEFAULTS
from viur.core.utils import currentRequest
from viur.core.config import conf


# ViURDefaultLogger ---------------------------------------------------------------------------------------------------

class ViURDefaultLogger(CloudLoggingHandler):
    """
    This is the ViUR-customized CloudLoggingHandler
    """

    def emit(self, record: logging.LogRecord):
        message = super(ViURDefaultLogger, self).format(record)
        try:
            currentReq = currentRequest.get()
            TRACE = "projects/{}/traces/{}".format(client.project, currentReq._traceID)
            currentReq.maxLogLevel = max(currentReq.maxLogLevel, record.levelno)
            logID = currentReq.request.environ.get("HTTP_X_APPENGINE_REQUEST_LOG_ID")
        except:
            TRACE = None
            logID = None

        self.transport.send(
            record,
            message,
            resource=self.resource,
            labels={
                "project_id": conf["viur.instance.project_id"],
                "module_id": "default",
                "version_id":
                    conf["viur.instance.app_version"]
                    if not conf["viur.instance.is_dev_server"]
                    else "dev_appserver",
            },
            trace=TRACE,
            operation={
                "first": False,
                "last": False,
                "id": logID
            }
        )


# ViURLocalFormatter ---------------------------------------------------------------------------------------------------

class ViURLocalFormatter(logging.Formatter):
    """
    This is a formatter that injects console color sequences for debug output.
    """

    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
    RESET_SEQ = "\033[0m"
    COLOR_SEQ = "\033[1;%dm"
    BOLD_SEQ = "\033[1m"

    LEVELS = {
        "WARNING": YELLOW,
        "INFO": CYAN,
        "DEBUG": BLUE,
        "CRITICAL": RED,
        "ERROR": RED
    }

    def format(self, record):
        if "pathname" in record.__dict__.keys():
            # truncate the pathname
            if "/deploy" in record.pathname:
                pathname = record.pathname.split("/deploy/")[1]
            else:
                pathname = record.pathname
                if len(pathname) > 20:
                    pathname = ".../" + "/".join(pathname.split("/")[-3:])

            record.pathname = pathname

        levelname = record.levelname

        if levelname in ViURLocalFormatter.LEVELS:
            record.levelname = ViURLocalFormatter.COLOR_SEQ % (30 + ViURLocalFormatter.LEVELS[levelname]) \
                               + levelname + ViURLocalFormatter.RESET_SEQ

        return super().format(record)


# Logger config

client = google.cloud.logging.Client()
requestLogger = client.logger("ViUR")
requestLoggingRessource = Resource(
    type="gae_app",
    labels={
       "project_id": conf["viur.instance.project_id"],
       "module_id": "default",
       "version_id": conf["viur.instance.app_version"] if not conf[
           "viur.instance.is_dev_server"] else "dev_appserver",
    }
)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

for loggerName, level in {
        k: v.getEffectiveLevel() for k, v in logging.root.manager.loggerDict.items() if isinstance(v, logging.Logger)
    }.items():
    logging.getLogger(loggerName).setLevel(level)

for handler in logger.handlers[:]:
    logger.removeHandler(handler)

if not conf["viur.instance.is_dev_server"]:
    handler = ViURDefaultLogger(client, name="ViUR-Messages", resource=Resource(type="gae_app", labels={}))
    logger.addHandler(handler)

    formatter = logging.Formatter("%(levelname)-8s %(asctime)s %(filename)s:%(lineno)s] %(message)s")
else:
    formatter = ViURLocalFormatter(
        f"[%(asctime)s] %(pathname)s:%(lineno)d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)

for logger_name in EXCLUDED_LOGGER_DEFAULTS:
    logger = logging.getLogger(logger_name)
    logger.propagate = False
    logger.addHandler(sh)
