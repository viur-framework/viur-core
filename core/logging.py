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
