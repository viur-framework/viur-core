import logging

import google.cloud.logging
from google.cloud.logging import Resource
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud.logging_v2.handlers.handlers import EXCLUDED_LOGGER_DEFAULTS

from viur.core.utils import currentRequest, projectID, appVersion, isLocalDevelopmentServer

client = google.cloud.logging.Client()
requestLoggingRessource = Resource(type="gae_app",
								   labels={
									   "project_id": projectID,
									   "module_id": "default",
									   "version_id": appVersion if not isLocalDevelopmentServer else "dev_appserver",
								   })

requestLogger = client.logger("ViUR")


class ViURDefaultLogger(CloudLoggingHandler):
	def emit(self, record):
		message = super(ViURDefaultLogger, self).format(record)
		try:
			currentReq = currentRequest.get()
			TRACE = "projects/{}/traces/{}".format(client.project, currentReq._traceID)
			currentReq.maxLogLevel = max(currentReq.maxLogLevel, record.levelno)
		except:
			TRACE = None

		self.transport.send(
			record,
			message,
			resource=self.resource,
			labels={
				"project_id": projectID,
				"module_id": "default",
				"version_id": appVersion if not isLocalDevelopmentServer else "dev_appserver",
			},
			trace=TRACE
		)


oldLevels = {k: v.getEffectiveLevel()
			 for k, v in logging.root.manager.loggerDict.items()
			 if isinstance(v, logging.Logger)}

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

for loggerName, level in oldLevels.items():
	logging.getLogger(loggerName).setLevel(level)

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
