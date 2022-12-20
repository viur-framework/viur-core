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
        "DEBUG": CYAN,
        "INFO": MAGENTA,
        "WARNING": YELLOW,
        "CRITICAL": RED,
        "ERROR": RED
    }

    def format(self, record: logging.LogRecord) -> str:
        # truncate the pathname
        if "/deploy" in record.pathname:
            pathname = record.pathname.split("/deploy/")[1]
        else:
            # When we have a module in a very deep package path, like
            # google.cloud.resourcemanager_v3.services.projects.client,
            # we turn it into something like google/.../projects/client.
            pathname = record.pathname
            if len(pathname) > 20:
                parts = pathname.split("/")
                del parts[1:-3]
                parts.insert(1, "...")
                pathname = "/".join(parts)

        record.pathname = pathname

        msg = super().format(record)

        # colorize entire message according to the levelname
        if record.levelname in ViURLocalFormatter.LEVELS:
            colorize = ViURLocalFormatter.COLOR_SEQ % (ViURLocalFormatter.LEVELS[record.levelname] + 30)
            return colorize + msg + ViURLocalFormatter.RESET_SEQ

        return msg


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

# Calling getLogger(name) ensures that any placeholder loggers held by loggerDict are fully initialized
# (https://stackoverflow.com/a/53250066)
for name, level in {
            k: v.getEffectiveLevel()
            for k, v in logging.root.manager.loggerDict.items()
            if isinstance(v, logging.Logger)
        }.items():
    logging.getLogger(name).setLevel(level)

# Remove any existing handler from logger
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Disable internal logging
# https://github.com/googleapis/python-logging/issues/13#issuecomment-539723753
for logger_name in EXCLUDED_LOGGER_DEFAULTS:
    excluded_logger = logging.getLogger(logger_name)
    excluded_logger.propagate = False
    excluded_logger.addHandler(logging.NullHandler())

if not conf["viur.instance.is_dev_server"]:
    # Plug-in ViURDefaultLogger
    handler = ViURDefaultLogger(client, name="ViUR-Messages", resource=Resource(type="gae_app", labels={}))
    logger.addHandler(handler)

else:
    # Use ViURLocalFormatter for local debug message formatting
    formatter = ViURLocalFormatter(f"[%(asctime)s] %(pathname)s:%(lineno)d [%(levelname)s] %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)
