# -*- coding: utf-8 -*-

# from google.appengine.api import memcache, app_identity, mail
# from google.appengine.ext import deferred
import os
from viur.core import db
import string, random, base64
from viur.core import conf
import logging
import google.auth
from datetime import datetime, timedelta
import hashlib
import hmac
from quopri import decodestring
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
import email.header
from typing import Any

# Determine which ProjectID we currently run in (as the app_identity module isn't available anymore)
_, projectID = google.auth.default()
del _


def generateRandomString(length: int = 13) -> str:
	"""
	Return a string containing random characters of given *length*.
	Its safe to use this string in URLs or HTML.

	:type length: int
	:param length: The desired length of the generated string.

	:returns: A string with random characters of the given length.
	:rtype: str
	"""
	return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def sendEMail(dests, name, skel, extraFiles=[], cc=None, bcc=None, replyTo=None, *args, **kwargs):
	"""
	General purpose function for sending e-mail.

	This function allows for sending e-mails, also with generated content using the Jinja2 template engine.

	:type dests: str | list of str
	:param dests: Full-qualified recipient email addresses; These can be assigned as list, for multiple targets.

	:type name: str
	:param name: The name of a template from the appengine/emails directory, or the template string itself.

	:type skel: server.skeleton.Skeleton | dict | None
	:param skel: The data made available to the template. In case of a Skeleton, its parsed the usual way;\
	Dictionaries are passed unchanged.

	:type extraFiles: list of fileobjects
	:param extraFiles: List of **open** fileobjects to be sent within the mail as attachments

	:type cc: str | list of str
	:param cc: Carbon-copy recipients

	:type bcc: str | list of str
	:param bcc: Blind carbon-copy recipients

	:type replyTo: str
	:param replyTo: A reply-to email address
	"""
	if conf["viur.emailRecipientOverride"]:
		logging.warning("Overriding destination %s with %s", dests, conf["viur.emailRecipientOverride"])

		oldDests = dests
		if isinstance(oldDests, str):
			oldDests = [oldDests]

		newDests = conf["viur.emailRecipientOverride"]
		if isinstance(newDests, str):
			newDests = [newDests]

		dests = []
		for newDest in newDests:
			if newDest.startswith("@"):
				for oldDest in oldDests:
					dests.append(oldDest.replace(".", "_dot_").replace("@", "_at_") + newDest)
			else:
				dests.append(newDest)

	elif conf["viur.emailRecipientOverride"] is False:
		logging.warning("Sending emails disabled by config[viur.emailRecipientOverride]")
		return

	handler = conf.get("viur.emailHandler")

	if handler is None:
		handler = _GAE_sendEMail

	if not callable(handler):
		logging.warning("Invalid emailHandler configured, no email will be sent.")
		return False

	logging.debug("CALLING %s" % str(handler))

	return handler(dests, name, skel, extraFiles=extraFiles, cc=cc, bcc=bcc, replyTo=replyTo, *args, **kwargs)


def _GAE_sendEMail(dests, name, skel, extraFiles=[], cc=None, bcc=None, replyTo=None, *args, **kwargs):
	"""
	Internal function for using Google App Engine Email processing API.
	"""
	headers, data = conf["viur.emailRenderer"](skel, name, dests, **kwargs)

	xheader = {}

	if "references" in headers:
		xheader["References"] = headers["references"]

	if "in-reply-to" in headers:
		xheader["In-Reply-To"] = headers["in-reply-to"]

	if xheader:
		message = mail.EmailMessage(headers=xheader)
	else:
		message = mail.EmailMessage()

	mailfrom = "viur@%s.appspotmail.com" % app_identity.get_application_id()

	if "subject" in headers:
		message.subject = "=?utf-8?B?%s?=" % base64.b64encode(headers["subject"].encode("UTF-8"))
	else:
		message.subject = "No Subject"

	if "from" in headers:
		mailfrom = headers["from"]

	if conf["viur.emailSenderOverride"]:
		mailfrom = conf["viur.emailSenderOverride"]

	if isinstance(dests, list):
		message.to = ", ".join(dests)
	else:
		message.to = dests

	if cc:
		if isinstance(cc, list):
			message.cc = ", ".join(cc)
		else:
			message.cc = cc

	if bcc:
		if isinstance(bcc, list):
			message.bcc = ", ".join(bcc)
		else:
			message.bcc = bcc

	if replyTo:
		message.reply_to = replyTo

	message.sender = mailfrom
	message.html = data.replace("\x00", "").encode('ascii', 'xmlcharrefreplace')

	if len(extraFiles) > 0:
		message.attachments = extraFiles
	message.send()
	return True


def sendEMailToAdmins(subject, body, sender=None):
	"""
		Sends an e-mail to the appengine administration of the current app.
		(all users having access to the applications dashboard)

		:param subject: Defines the subject of the message.
		:type subject: str

		:param body: Defines the message body.
		:type body: str

		:param sender: (optional) specify a different sender
		:type sender: str
	"""
	if not sender:
		sender = "viur@%s.appspotmail.com" % app_identity.get_application_id()

	mail.send_mail_to_admins(sender, "=?utf-8?B?%s?=" % base64.b64encode(subject.encode("UTF-8")),
							 body.encode('ascii', 'xmlcharrefreplace'))


def getCurrentUser():
	"""
		Retrieve current user, if logged in.

		If a user is logged in, this function returns a dict containing user data.

		If no user is logged in, the function returns None.

		:rtype: dict | bool
		:returns: A dict containing information about the logged-in user, None if no user is logged in.
	"""
	user = None
	if "user" in dir(conf["viur.mainApp"]):  # Check for our custom user-api
		user = conf["viur.mainApp"].user.getCurrentUser()
	return user


def markFileForDeletion(dlkey):
	"""
	Adds a marker to the data store that the file specified as *dlkey* can be deleted.

	Once the mark has been set, the data store is checked four times (default: every 4 hours)
	if the file is in use somewhere. If it is still in use, the mark goes away, otherwise
	the mark and the file are removed from the datastore. These delayed checks are necessary
	due to database inconsistency.

	:type dlkey: str
	:param dlkey: Unique download-key of the file that shall be marked for deletion.
	"""
	fileObj = db.Query("viur-deleted-files").filter("dlkey", dlkey).get()

	if fileObj:  # Its allready marked
		return

	fileObj = db.Entity("viur-deleted-files")
	fileObj["itercount"] = 0
	fileObj["dlkey"] = str(dlkey)
	db.Put(fileObj)


def escapeString(val, maxLength=254):
	"""
		Quotes several characters and removes "\\\\n" and "\\\\0" to prevent XSS injection.

		:param val: The value to be escaped.
		:type val: str

		:param maxLength: Cut-off after maxLength characters. A value of 0 means "unlimited".
		:type maxLength: int

		:returns: The quoted string.
		:rtype: str
	"""
	val = str(val).strip() \
		.replace("<", "&lt;") \
		.replace(">", "&gt;") \
		.replace("\"", "&quot;") \
		.replace("'", "&#39;") \
		.replace("\n", "") \
		.replace("\0", "")

	if maxLength:
		return val[0:maxLength]

	return val


def hmacSign(data: Any) -> str:
	if not isinstance(data, bytes):
		data = str(data).encode("UTF-8")
	return hmac.new(conf["viur.file.hmacKey"], msg=data, digestmod=hashlib.sha3_384).hexdigest()


def hmacVerify(data: Any, signature: str) -> bool:
	return hmac.compare_digest(hmacSign(data), signature)


def downloadUrlFor(folder: str, fileName: str, derived: bool = False, expires: timedelta = timedelta(hours=1)) -> str:
	if derived:
		filePath = "%s/derived/%s" % (folder, fileName)
	else:
		filePath = "%s/source/%s" % (folder, fileName)
	sigStr = "%s\0%s" % (filePath, ((datetime.now() + expires).strftime("%Y%m%d%H%M") if expires else 0))
	sigStr = urlsafe_b64encode(sigStr.encode("UTF-8"))
	resstr = hmacSign(sigStr)
	return "/file/download/%s?sig=%s" % (sigStr.decode("ASCII"), resstr)

def seoUrlToEntry(module, entry=None, skelType=None, language=None):
	from viur.core import request, conf
	lang = request.current.get().language
	if module in conf["viur.languageModuleMap"] and lang in conf["viur.languageModuleMap"][module]:
		module = conf["viur.languageModuleMap"][module][lang]
	if not entry:
		return "/%s/%s" % (lang, module)
	#elif isinstance(entry, dict):
	else:
		try:
			currentSeoKeys = entry.get("viurCurrentSeoKeys")
		except:
			return "/%s/%s" % (lang, module)
		if lang in (currentSeoKeys or {}):
			seoKey = currentSeoKeys[lang]
		elif "key" in entry:
			seoKey = entry["key"]
		elif "name" in dir(entry):
			seoKey = entry.name
		else:
			return "/%s/%s" % (lang, module)
		return "/%s/%s/%s" % (lang, module, seoKey)

def seoUrlToFunction(module, function, render=None):
	from viur.core import request, conf
	lang = request.current.get().language
	if module in conf["viur.languageModuleMap"] and lang in conf["viur.languageModuleMap"][module]:
		module = conf["viur.languageModuleMap"][module][lang]
	pathComponents = ["", lang]
	targetObject = conf["viur.mainResolver"]
	if module in targetObject:
		pathComponents.append(module)
		targetObject = targetObject[module]
	if render and render in targetObject:
		pathComponents.append(render)
		targetObject = targetObject[render]
	if function in targetObject:
		func = targetObject[function]
		if getattr(func, "seoLanguageMap", None) and lang in func.seoLanguageMap:
			pathComponents.append(func.seoLanguageMap[lang])
		else:
			pathComponents.append(function)
	return "/".join(pathComponents)


