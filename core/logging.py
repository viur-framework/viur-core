import logging
import google.cloud.logging
from google.cloud.logging import Resource
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud.logging_v2.handlers.handlers import EXCLUDED_LOGGER_DEFAULTS

from viur.core.utils import currentRequest
from viur.core.config import conf

client = google.cloud.logging.Client()
requestLoggingRessource = Resource(type="gae_app",
                                   labels={
                                       "project_id": conf["viur.instance.project_id"],
                                       "module_id": "default",
                                       "version_id": conf["viur.instance.app_version"] if not conf[
                                           "viur.instance.is_dev_server"] else "dev_appserver",
                                   })

requestLogger = client.logger("ViUR")


class ViURDefaultLogger(CloudLoggingHandler):
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


oldLevels = {k: v.getEffectiveLevel()
             for k, v in logging.root.manager.loggerDict.items()
             if isinstance(v, logging.Logger)}

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

for loggerName, level in oldLevels.items():
    logging.getLogger(loggerName).setLevel(level)

for handler in logger.handlers[:]:
    logger.removeHandler(handler)

handler = ViURDefaultLogger(client, name="ViUR-Messages", resource=Resource(type="gae_app", labels={}))
logger.addHandler(handler)

sh = logging.StreamHandler()
formatter = logging.Formatter("%(levelname)-8s %(asctime)s %(filename)s:%(lineno)s] %(message)s")
sh.setFormatter(formatter)
logger.addHandler(sh)

for logger_name in EXCLUDED_LOGGER_DEFAULTS:
    logger = logging.getLogger(logger_name)
    logger.propagate = False
    logger.addHandler(sh)


BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

LEVELS = {
    "WARNING": YELLOW,
    "INFO": CYAN,
    "DEBUG": MAGENTA,
    "CRITICAL": RED,
    "ERROR": RED
}


class ViURLocalFormatter(logging.Formatter):
    def format(self, record):
        if "pathname" in record.__dict__.keys():
            # truncate the pathname
            if "/deploy" in record.pathname:
                pathname = "." + record.pathname.split("/deploy")[1]
            else:
                pathname = record.pathname
                if len(pathname) > 20:
                    pathname = ".../" + "/".join(pathname.split("/")[-3:])
            record.pathname = pathname

        levelname = record.levelname

        if levelname in LEVELS:
            levelname_color = COLOR_SEQ % (30 + LEVELS[levelname]) + levelname + RESET_SEQ
            record.levelname = levelname_color

        return super().format(record)


if conf["viur.instance.is_dev_server"]:
    logger = logging.getLogger()

    if True:  # fixme: Provide a conf-flag for this!
        logger.handlers = []  # don't upload logs to gcloud
    else:
        for handler in logger.handlers:
            if not isinstance(handler, ViURDefaultLogger):
                logger.removeHandler(handler)

    logger.setLevel(logging.DEBUG)

    sh = logging.StreamHandler()
    formatter = ViURLocalFormatter(
        f"[%(asctime)s] %(pathname)s:%(lineno)d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    sh.setFormatter(formatter)
    logger.addHandler(sh)
