# -*- coding: utf-8 -*-

from google.appengine.api import memcache, app_identity, mail
from google.appengine.ext import deferred
import new, os
from server import db
import string, random, base64
from server import conf
import logging
from itertools import izip


def generateRandomString( length=13 ):
	"""
	Return a string containing random characters of given *length*.
	Its safe to use this string in URLs or HTML.
	
	:type length: int
	:param length: The desired length of the generated string.

	:returns: A string with random characters of the given length.
	:rtype: str
	"""
	return( ''.join( [
				random.choice( string.ascii_lowercase + string.ascii_uppercase + string.digits )
				for x in range( length ) ] ) )

	
def sendEMail( dests, name, skel, extraFiles=[], cc=None, bcc=None, replyTo=None ):
	"""
	General purpose function for sending e-mail.

	This function allows for sending e-mails, also with generated content using the Jinja2 template engine.

	:type dests: str | list of str
	:param dests: Full-qualified recipient email addresses; These can be assigned as list, for multiple targets.

	:type name: str
	:param name: The name of a template from the appengine/emails directory, or the template string itself.

	:type skel: server.skeleton.Skeleton | dict | None
	:param skel: The data made available to the template. In case of a Skeleton, its parsed the usual way;\
	Dictionarys are passed unchanged.

	:type extraFiles: list of fileobjects
	:param extraFiles: List of **open** fileobjects to be sent within the mail as attachments

	:type cc: str | list of str
	:param cc: Carbon-copy recipients

	:type bcc: str | list of str
	:param bcc: Blind carbon-copy recipients

	:type replyTo: str
	:param replyTo: A reply-to email address
	"""

	def rewriteEmail(oldDests, newDest):
		"""
			Rewrites each address in *oldDests* so that it will end with @newDest
			:param oldDests: EMail-Address (or a list hereof) to rewrite
			:type oldDests: str | list[str]
			:param newDest: New Destination-Domain (eg "@mausbrand.de")
			:type newDest: str
			:return:
		"""
		if isinstance( oldDests, list ):
			return [rewriteEmail(x) for x in oldDests ]
		else:
			newAddress = oldDests.replace(".", "_dot_").replace("@", "_at_")
			return "%s%s" % (newAddress, newDest)

	if conf["viur.emailRecipientOverride"]:
		logging.warning("Overriding destination %s with %s", dests, conf["viur.emailRecipientOverride"])
		if conf["viur.emailRecipientOverride"].startswith("@"):
			dests = rewriteEmail(dests, conf["viur.emailRecipientOverride"])
		else:
			dests = conf["viur.emailRecipientOverride"]
	elif conf["viur.emailRecipientOverride"] is False:
		logging.warning("Sending emails disabled by config[viur.emailRecipientOverride]")
		return

	headers, data = conf["viur.emailRenderer"]( skel, name, dests )
	xheader = {}

	if "references" in headers.keys():
		xheader["References"] = headers["references"]

	if "in-reply-to" in headers.keys():
		xheader["In-Reply-To"] = headers["in-reply-to"]	

	if xheader:
		message = mail.EmailMessage(headers=xheader)
	else:
		message = mail.EmailMessage()


	mailfrom = "viur@%s.appspotmail.com" % app_identity.get_application_id()

	if "subject" in headers.keys():
		message.subject =  "=?utf-8?B?%s?=" % base64.b64encode( headers["subject"].encode("UTF-8") )
	else:
		message.subject = "No Subject"

	if "from" in headers.keys():
		mailfrom = headers["from"]

	if conf["viur.emailSenderOverride"]:
		mailfrom = conf["viur.emailSenderOverride"]

	if isinstance( dests, list ):
		message.to = ", ".join( dests )
	else:
		message.to = dests

	if cc:
		if isinstance( cc, list ):
			message.cc = ", ".join( cc )
		else:
			message.cc = cc

	if bcc:
		if isinstance( bcc, list ):
			message.bcc = ", ".join( bcc )
		else:
			message.bcc = bcc

	if replyTo:
		message.reply_to = replyTo

	message.sender = mailfrom
	message.html = data.replace("\x00","").encode('ascii', 'xmlcharrefreplace')

	if len( extraFiles )> 0:
		message.attachments = extraFiles
	
	message.send( )

def sendEMailToAdmins( subject, body, sender=None ):
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

	mail.send_mail_to_admins( sender, "=?utf-8?B?%s?=" % base64.b64encode( subject.encode("UTF-8") ),
	                          body.encode('ascii', 'xmlcharrefreplace') )

def getCurrentUser( ):
	"""
		Retrieve current user, if logged in.

		If a user is logged in, this function returns a dict containing user data.

		If no user is logged in, the function returns None.

		:rtype: dict | bool
		:returns: A dict containing information about the logged-in user, None if no user is logged in.
	"""
	user = None

	if "user" in dir( conf["viur.mainApp"] ): #Check for our custom user-api
		user = conf["viur.mainApp"].user.getCurrentUser()

	return( user )

def markFileForDeletion( dlkey ):
	"""
	Adds a marker to the data store that the file specified as *dlkey* can be deleted.

	Once the mark has been set, the data store is checked four times (default: every 4 hours)
	if the file is in use somewhere. If it is still in use, the mark goes away, otherwise
	the mark and the file are removed from the datastore. These delayed checks are necessary
	due to database inconsistency.
	
	:type dlkey: str
	:param dlkey: Unique download-key of the file that shall be marked for deletion.
	"""
	fileObj = db.Query( "viur-deleted-files" ).filter( "dlkey", dlkey ).get()

	if fileObj: #Its allready marked
		return

	fileObj = db.Entity( "viur-deleted-files" )
	fileObj["itercount"] = 0
	fileObj["dlkey"] = str( dlkey )
	db.Put( fileObj )

def escapeString( val, maxLength=254 ):
	"""
		Quotes several characters and removes "\\\\n" and "\\\\0" to prevent XSS injection.

		:param val: The value to be escaped.
		:type val: str

		:param maxLength: Cut-off after maxLength characters. A value of 0 means "unlimited".
		:type maxLength: int

		:returns: The quoted string.
		:rtype: str
	"""
	val = unicode(val).strip() \
			.replace("<", "&lt;") \
			.replace(">", "&gt;") \
			.replace("\"", "&quot;") \
			.replace("'", "&#39;") \
			.replace("\n","") \
			.replace("\0","")

	if maxLength:
		return( val[0:maxLength] )

	return( val )


def safeStringComparison(s1, s2):
	"""
		Performs a string comparison in constant time.
		This should prevent side-channel (timing) attacks
		on passwords etc.
		:param s1: First string to compare
		:type s1: string | unicode
		:param s2: Second string to compare
		:type s2: string | unicode
		:return: True if both strings are equal, False otherwise
		:return type: bool
	"""
	isOkay = True
	if type(s1) != type(s2):
		isOkay = False  # We have a unicode/str messup here
	if len(s1) != len(s2):
		isOkay = False
	for x, y in izip(s1, s2):
		if x != y:
			isOkay = False
	return isOkay

def normalizeKey( key ):
	"""
		Normalizes a datastore key (replacing _application with the current one)
	:param key:
	:return:
	"""
	if key is None:
		return None
	key = db.Key(encoded=str(key))
	if key.parent():
		parent = db.Key(encoded=normalizeKey(key.parent()))
	else:
		parent = None
	return str( db.Key.from_path(key.kind(), key.id_or_name(), parent=parent))

