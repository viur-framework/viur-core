# -*- coding: utf-8 -*-
import logging, os
from typing import Any, Union, List, Dict, Tuple
from viur.core.config import conf
from viur.core import db, utils
from viur.core.utils import projectID
from viur.core.tasks import callDeferred, QueryIter, PeriodicTask
import json, base64
from urllib import request

"""
	This module implements an email delivery system for ViUR. Emails will be queued so that we don't overwhelm
	the email service. As the Appengine does not provide an email-api anymore, you'll have to use a 3rd party service
	to actually deliver the email. A sample implementation for Send in Blue (https://sendinblue.com/) is provided.
	To enable Send in Blue,	set conf["viur.email.transportFunction"] to transportSendInBlue and add your API-Key to
	conf["viur.email.sendInBlue.apiKey"]. To send via another service, you'll have to implement a different transport
	function (and point conf["viur.email.transportFunction"] to that function). This module needs a custom queue
	(viur-emails) with a larger backoff value (sothat we don't try to deliver the same email multiple times within a
	short timeframe). A suggested configuration would be
	
	- name: viur-emails
		rate: 1/s
		retry_parameters:
			min_backoff_seconds: 3600
			max_backoff_seconds: 3600

"""

@PeriodicTask(interval=60*24)
def cleanOldEmailsFromLog(*args, **kwargs):
	"""
		Start the QueryIter DeleteOldEmailsFromLog to remove old, successfully send emails from the queue
	"""
	qry = db.Query("viur-emails").filter("isSend =", True) \
		.filter("creationDate <", utils.utcNow()-conf["viur.email.logRetention"])
	DeleteOldEmailsFromLog.startIterOnQuery(qry)

class DeleteOldEmailsFromLog(QueryIter):
	"""
		Simple Query-Iter to delete all entities encountered
	"""
	@classmethod
	def handleEntry(cls, entry, customData):
		db.Delete(entry.key)


@callDeferred
def sendEmailDeferred(emailKey: db.KeyClass):
	"""
		Callback from the Taskqueue to send the given Email
		:param emailKey: Database-Key of the email we should send
	"""
	logging.debug("Sending deferred email: %s" % str(emailKey))
	queueEntity = db.Get(emailKey)
	assert queueEntity, "Email queue object went missing!"
	if queueEntity["isSend"]:
		return True
	elif queueEntity["errorCount"] > 3:
		raise ChildProcessError("Error-Count exceeded")
	transportFunction = conf["viur.email.transportFunction"] # First, ensure we're able to send email at all
	assert callable(transportFunction), "No or invalid email transportfunction specified!"
	try:
		resultData = transportFunction(dests=queueEntity["dests"],
									   sender=queueEntity["sender"],
									   cc=queueEntity["cc"],
									   bcc=queueEntity["bcc"],
									   subject=queueEntity["subject"],
									   body=queueEntity["body"],
									   headers=queueEntity["headers"],
									   attachments=queueEntity["attachments"])
	except Exception:
		# Increase the errorCount and bail out
		queueEntity["errorCount"] += 1
		db.Put(queueEntity)
		raise
	# If that transportFunction did not raise an error that email has been successfully send
	queueEntity["isSend"] = True
	queueEntity["sendDate"] = utils.utcNow()
	queueEntity["transportFuncResult"] = resultData
	queueEntity.exclude_from_indexes.add("transportFuncResult")
	db.Put(queueEntity)
	if conf["viur.email.transportSuccessful"]:
		try:
			conf["viur.email.transportSuccessful"](queueEntity)
		except Exception as e:
			logging.exception(e)
			


def normalizeToList(value: Union[None, Any, List[Any]]) -> List[Any]:
	"""
		Convert the given value to a list.
	"""
	if value is None:
		return []
	if isinstance(value, list):
		return value
	return [value]

def sendEMail(*,
			  tpl: str = None,
			  stringTemplate: str = None,
			  skel: Union[None, Dict, "SkeletonInstance", List["SkeletonInstance"]] = None,
			  sender: str = None,
			  dests: Union[str, List[str]] = None,
			  cc: Union[str, List[str]] = None,
			  bcc: Union[str, List[str]] = None,
			  headers: Dict[str, str] = None,
			  attachments: List[Dict[str, Any]] = None,
			  **kwargs) -> Any:
	"""
	General purpose function for sending e-mail.
	This function allows for sending e-mails, also with generated content using the Jinja2 template engine.
	Your have to implement a method which should be called to send the prepared email finally. For this you have
	to allocate *viur.email.transportFunction* in conf.

	:param tpl: The name of a template from the deploy/emails directory.
	:param stringTemplate: This string is interpreted as the template contents. Alternative to load from template file.
		:param skel: The data made available to the template. In case of a Skeleton or SkelList, its parsed the usual way;\
		Dictionaries are passed unchanged.
	:param sender: The address sending this mail.
	:param dests: A list of addresses to send this mail to. A bare string will be treated as a list with 1 address.
	:param cc: Carbon-copy recipients. A bare string will be treated as a list with 1 address.
	:param bcc: Blind carbon-copy recipients. A bare string will be treated as a list with 1 address.
	:param headers: Specify headers for this email.
	:param attachments: List of files to be sent within the mail as attachments. Each attachment must be a dictionary
		with these keys:
			filename (string): Name of the file that's attached. Always required
			content (bytes): Content of the attachment as bytes. Required for the send in blue API.
			mimetype (string): Mimetype of the file. Suggested parameter for other implementations (not used by SIB)
			gcsfile (string): Link to a GCS-File to include instead of content. Not supported by the current
				SIB implementation

	.. Warning:  As emails will be queued (and not send directly) you cannot exceed 1MB in total
				(for all text and attachments combined)!
	"""
	# First, ensure we're able to send email at all
	assert callable(conf.get("viur.email.transportFunction")), "No or invalid email transportfunction specified!"
	# Ensure that all recipient parameters (dest, cc, bcc) are a list
	dests = normalizeToList(dests)
	cc = normalizeToList(cc)
	bcc = normalizeToList(bcc)
	assert dests or cc or bcc, "No destination address given"
	attachments = normalizeToList(attachments)
	if not (bool(stringTemplate) ^ bool(tpl)):
		raise ValueError("You have to set the params 'tpl' xor a 'stringTemplate'.")
	if attachments:
		# Ensure each attachment has the filename key and rewrite each dict to db.Entity so we can exclude
		# it from being indexed
		for _ in range(0, len(attachments)):
			attachment = attachments.pop(0)
			assert "filename" in attachment
			entity = db.Entity()
			for k, v in attachment.items():
				entity[k] = v
				entity.exclude_from_indexes.add(k)
			attachments.append(entity)
		assert all(["filename" in x for x in attachments]), "Attachment is missing the filename key"
	# If conf["viur.email.recipientOverride"] is set we'll redirect any email to these address(es)
	if conf["viur.email.recipientOverride"]:
		logging.warning("Overriding destination %s with %s", dests, conf["viur.email.recipientOverride"])
		oldDests = dests
		newDests = normalizeToList(conf["viur.email.recipientOverride"])
		dests = []
		for newDest in newDests:
			if newDest.startswith("@"):
				for oldDest in oldDests:
					dests.append(oldDest.replace(".", "_dot_").replace("@", "_at_") + newDest)
			else:
				dests.append(newDest)
		cc = bcc = []
	elif conf["viur.email.recipientOverride"] is False:
		logging.warning("Sending emails disabled by config[viur.email.recipientOverride]")
		return False
	if conf["viur.email.senderOverride"]:
		sender = conf["viur.email.senderOverride"]
	elif sender is None:
		sender = f"viur@{projectID}.appspotmail.com"
	subject, body = conf["viur.emailRenderer"](dests, tpl, stringTemplate, skel, **kwargs)
	# Push that email to the outgoing queue
	queueEntity = db.Entity(db.Key("viur-emails"))
	queueEntity["isSend"] = False
	queueEntity["errorCount"] = 0
	queueEntity["creationDate"] = utils.utcNow()
	queueEntity["sender"] = sender
	queueEntity["dests"] = dests
	queueEntity["cc"] = cc
	queueEntity["bcc"] = bcc
	queueEntity["subject"] = subject
	queueEntity["body"] = body
	queueEntity["headers"] = headers
	queueEntity["attachments"] = attachments
	queueEntity.exclude_from_indexes = ["body", "attachments"]
	if utils.isLocalDevelopmentServer and not conf["viur.email.sendFromLocalDevelopmentServer"]:
		logging.info("Not sending email from local development server")
		logging.info("Subject: %s", queueEntity["subject"])
		logging.info("Body: %s", queueEntity["body"])
		logging.info("Recipients: %s", queueEntity["dests"])
		return False
	db.Put(queueEntity)
	sendEmailDeferred(queueEntity.key, _queue="viur-emails")
	return True


def sendEMailToAdmins(subject: str, body: str, *args, **kwargs):
	"""
		Sends an e-mail to the root users of the current app.

		:param subject: Defines the subject of the message.
		:param body: Defines the message body.
	"""
	success = False
	try:
		if "user" in dir(conf["viur.mainApp"]):
			users = []
			for userSkel in conf["viur.mainApp"].user.viewSkel().all().filter("access =", "root").fetch():
				users.append(userSkel["name"])

			if users:
				ret = sendEMail(dests=users, stringTemplate=os.linesep.join((subject, body)), *args, **kwargs)
				success = True
				return ret
			else:
				logging.warning("There are no root-users.")

	except Exception:
		raise

	finally:
		if not success:
			logging.critical("Cannot send mail to Admins.")
			logging.critical("Subject of mail: %s", subject)
			logging.critical("Content of mail: %s", body)

	return False

def transportSendInBlue(*, sender: str, dests: List[str], cc: List[str], bcc: List[str], subject: str, body: str,
				  headers: Dict[str, str], attachments: List[Dict[str, bytes]], **kwargs):
	"""
		Internal function for delivering Emails using Send in Blue. This function requires the
		conf["viur.email.sendInBlue.apiKey"] to be set.
		This function is supposed to return on success and throw an exception otherwise.
		If no exception is thrown, the email is considered send and will not be retried.

	"""
	def splitAddress(address: str) -> Dict[str, str]:
		"""
			Splits an Name/Address Pair as "Max Musterman <mm@example.com>" into a dict
			{"name": "Max Mustermann", "email": "mm@example.com"}
			:param address: Name/Address pair
			:return: Splitted dict
		"""
		posLt = address.rfind("<")
		posGt = address.rfind(">")
		if -1 < posLt < posGt:
			email = address[posLt + 1:posGt]
			sname = address.replace("<%s>" % email, "", 1).strip()
			return {"name": sname, "email": email}
		else:
			return {"email": address}

	dataDict = {
		"sender": splitAddress(sender),
		"to": [],
		"htmlContent": body,
		"subject": subject,
	}
	for dest in dests:
		dataDict["to"].append(splitAddress(dest))
	for dest in bcc:
		dataDict["bcc"].append(splitAddress(dest))
	for dest in cc:
		dataDict["cc"].append(splitAddress(dest))
	if headers:
		if "Reply-To" in headers:
			dataDict["replyTo"] = splitAddress(headers["Reply-To"])
			del headers["Reply-To"]
		if headers:
			dataDict["headers"] = headers
	if attachments:
		dataDict["attachment"] = []
		for attachment in attachments:
			dataDict["attachment"].append({
				"name": attachment["filename"],
				"content": base64.b64encode(attachment["content"]).decode("ASCII")
			})
	payload = json.dumps(dataDict).encode("UTF-8")
	headers = {
		"api-key": conf["viur.email.sendInBlue.apiKey"],
		"Content-Type": "application/json; charset=utf-8"
	}
	reqObj = request.Request(url="https://api.sendinblue.com/v3/smtp/email",
							 data=payload, headers=headers, method="POST")
	try:
		response = request.urlopen(reqObj)
	except request.HTTPError as e:
		logging.error("Sending email failed!")
		logging.error(dataDict)
		logging.error(e.read())
		raise
	assert str(response.code)[0]=="2", "Received a non 2XX Status Code!"
	return response.read().decode("UTF-8")
