# -*- coding: utf-8 -*-

import logging
import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud.logging.resource import Resource
from viur.core.utils import projectID, currentRequest

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


handler = ViURDefaultLogger(client, name="ViUR-Messages", resource=Resource(type="gae_app", labels={}))
google.cloud.logging.handlers.setup_logging(handler)
logging.getLogger().setLevel(logging.DEBUG)
