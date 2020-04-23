# -*- coding: utf-8 -*-
import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud.logging.handlers.handlers import EXCLUDED_LOGGER_DEFAULTS
from google.cloud.logging.resource import Resource
import logging
from viur.core.utils import currentRequest, projectID


client = google.cloud.logging.Client()
requestLoggingRessource = Resource(type="gae_app",
								   labels={
									   "project_id": projectID,
									   "module_id": "default",
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
			labels=self.labels,
			trace=TRACE
		)


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

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
