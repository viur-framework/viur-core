import os
import logging
import google.cloud.logging
from google.cloud.logging import Resource
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud.logging_v2.handlers.handlers import EXCLUDED_LOGGER_DEFAULTS
from viur.core import current
from viur.core.config import conf


# ViURDefaultLogger ---------------------------------------------------------------------------------------------------

class ViURDefaultLogger(CloudLoggingHandler):
    """
    This is the ViUR-customized CloudLoggingHandler
    """

    def emit(self, record: logging.LogRecord):
        message = super(ViURDefaultLogger, self).format(record)
        try:
            currentReq = current.request.get()
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

    The formatting can be modified using environment variables as follows:

    - VIUR_LOGGING_COLORIZATION can be either FULL (colorize full line) or DECENT (colorize debug level only)
    - VIUR_LOGGING_COLOR_DEBUG set debug level color
    - VIUR_LOGGING_COLOR_INFO set info level color
    - VIUR_LOGGING_COLOR_WARNING set warning level color
    - VIUR_LOGGING_COLOR_ERROR set error level color
    - VIUR_LOGGING_COLOR_CRITICAL set critical error level color

    The colors can be "black", "red", "green", "yellow", "blue", "magenta", "cyan" and "white".

    Example configuration using viur-cli
    ```sh
    VIUR_LOGGING_COLOR_WARNING=red VIUR_LOGGING_COLORIZATION=decent pipenv run viur run develop
    ```

    For details on console coloring, see https://en.wikipedia.org/wiki/ANSI_escape_code#Colors.
    """
    COLORS = {
        name: idx for idx, name in enumerate(("BLACK", "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "CYAN", "WHITE"))
    }

    DEFAULTS = {
        "DEBUG": "CYAN",
        "INFO": "MAGENTA",
        "WARNING": "YELLOW",
        "ERROR": "RED",
        "CRITICAL": "RED",
    }

    @staticmethod
    def colorize(level: str, text: str) -> str:
        """
        Retrieving colors for given debug level, either from environment or by default.
        """
        level = level.upper()
        color = os.getenv(f"VIUR_LOGGING_COLOR_{level}") or ViURLocalFormatter.DEFAULTS.get(level)
        color = ViURLocalFormatter.COLORS.get(color.upper(), 1)
        return f"\033[1;{color + 30}m{text}\033[0m"

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

        # Select colorization mode
        match (os.getenv(f"VIUR_LOGGING_COLORIZATION") or "FULL").upper():
            case "DECENT":
                # In "decent" mode, just colorize the record level name
                record.levelname = ViURLocalFormatter.colorize(record.levelname, record.levelname)

            case _:
                # Otherwise, colorize the entire debug output
                return ViURLocalFormatter.colorize(record.levelname, super().format(record))

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
