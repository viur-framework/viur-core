# -*- coding: utf-8 -*-
import hashlib
import hmac
import os
import random
import string
from base64 import urlsafe_b64encode
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Union
import google.auth
from viur.core import conf, db


# Proxy to context depended variables
currentRequest = ContextVar("Request", default=None)
currentRequestData = ContextVar("Request-Data", default=None)
currentSession = ContextVar("Session", default=None)
currentLanguage = ContextVar("Language", default=None)

# Determine which ProjectID we currently run in (as the app_identity module isn't available anymore)
_, projectID = google.auth.default()
del _
# Determine our basePath (as os.getCWD is broken on appengine)
projectBasePath = globals()["__file__"].replace("/viur/core/utils.py","")
isLocalDevelopmentServer = os.environ['GAE_ENV'] == "localdev"


def utcNow():
	return datetime.now(timezone.utc)

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
	fileObj = db.Query("viur-deleted-files").filter("dlkey", dlkey).getEntry()

	if fileObj:  # Its allready marked
		return

	fileObj = db.Entity(db.Key("viur-deleted-files"))
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
	assert conf["viur.file.hmacKey"] is not None, "No hmac-key set!"
	if not isinstance(data, bytes):
		data = str(data).encode("UTF-8")
	return hmac.new(conf["viur.file.hmacKey"], msg=data, digestmod=hashlib.sha3_384).hexdigest()


def hmacVerify(data: Any, signature: str) -> bool:
	return hmac.compare_digest(hmacSign(data), signature)


def downloadUrlFor(folder: str, fileName: str, derived: bool = False,
				   expires: Union[timedelta, None] = timedelta(hours=1)) -> str:
	"""
		Utility function that creates a signed download-url for the given folder/filename combination

		:param folder: The GCS-Folder (= the download-key) for that file
		:param fileName: The name of that file. Either the original filename as uploaded or the name of a dervived file
		:param derived: True, if it points to a derived file, False if it points to the original uploaded file
		:param expires: None if the file is supposed to be public (which causes it to be cached on the google ede
			caches), otherwise a timedelta of how long that link should be valid
		:return: THe signed download-url relative to the current domain (eg /download/...)
	"""
	if derived:
		filePath = "%s/derived/%s" % (folder, fileName)
	else:
		filePath = "%s/source/%s" % (folder, fileName)
	sigStr = "%s\0%s" % (filePath, ((datetime.now() + expires).strftime("%Y%m%d%H%M") if expires else 0))
	sigStr = urlsafe_b64encode(sigStr.encode("UTF-8"))
	resstr = hmacSign(sigStr)
	return "/file/download/%s?sig=%s" % (sigStr.decode("ASCII"), resstr)


def seoUrlToEntry(module, entry=None, skelType=None, language=None):
	from viur.core import conf
	pathComponents = [""]
	lang = currentLanguage.get()
	if conf["viur.languageMethod"] == "url":
		pathComponents.append(lang)
	if module in conf["viur.languageModuleMap"] and lang in conf["viur.languageModuleMap"][module]:
		module = conf["viur.languageModuleMap"][module][lang]
	pathComponents.append(module)
	if not entry:
		return "/".join(pathComponents)
	else:
		try:
			currentSeoKeys = entry["viurCurrentSeoKeys"]
		except:
			return "/".join(pathComponents)
		if lang in (currentSeoKeys or {}):
			pathComponents.append(str(currentSeoKeys[lang]))
		elif "key" in entry:
			pathComponents.append(str(entry["key"]))
		elif "name" in dir(entry):
			pathComponents.append(str(entry.name))
		return "/".join(pathComponents)


def seoUrlToFunction(module, function, render=None):
	from viur.core import conf
	lang = currentLanguage.get()
	if module in conf["viur.languageModuleMap"] and lang in conf["viur.languageModuleMap"][module]:
		module = conf["viur.languageModuleMap"][module][lang]
	if conf["viur.languageMethod"] == "url":
		pathComponents = ["", lang]
	else:
		pathComponents = [""]
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


def normalizeKey(key: Union[None, 'db.KeyClass']) -> Union[None, 'db.KeyClass']:
	"""
		Normalizes a datastore key (replacing _application with the current one)

		:param key: Key to be normalized.

		:return: Normalized key in string representation.
	"""
	if key is None:
		return None
	if key.parent:
		parent = normalizeKey(key.parent)
	else:
		parent = None
	return db.Key(key.kind, key.id_or_name, parent=parent)
