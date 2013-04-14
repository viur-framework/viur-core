# -*- coding: utf-8 -*-
from google.appengine.api import memcache, app_identity, mail
from google.appengine.ext import deferred
import new, os
from server.bones import baseBone
from server.session import current
from server import db
import string, random, base64
from google.appengine.api import search
from server.config import conf
from datetime import datetime, timedelta
import logging


def generateRandomString( length=13 ):
	"""Returns a new random String of the given length.
	Its safe to use this string in urls or html.
	
	@type length: Int
	@name length: Length of the generated String
	@return: A new random String of the given length
	"""
	return(  ''.join( [ random.choice(string.ascii_lowercase+string.ascii_uppercase + string.digits) for x in range(13) ] ) )

def createSecurityKey( duration=None, **kwargs ):
	"""
		Creates a new onetime Securitykey for the current session
		If duration is not set, this key is valid only for the current session.
		Otherwise, the key and its data is serialized and saved inside the datastore
		for up to duration-seconds
		@param duration: Make this key valid for a fixed timeframe (and independend of the current session)
		@type duration: Int or None
		@returns: The new onetime key
		
		Fixme: We have a race-condition here.
		If the user issues two requests at the same time, its possible that a freshly generated skey is lost
		or a skey consumed by one of these requests become avaiable again
	"""
	key = generateRandomString()
	return( key )
	if duration: #Create a longterm key in the datastore
		dbObj = db.Entity("viur_security_keys" )
		for k, v in kwargs.items():
			dbObj[ k ] = v
		dbObj["until"] = datetime.now()+timedelta( seconds=duration )
		dbObj["skey"] = key
		dbObj.set_unindexed_properties( [x for x in dbObj.keys() if not x in ["skey", "until"] ] )
		db.Put( dbObj )
	else: #Create an session-dependet key
		keys = current.get( "skeys" )
		if not keys:
			keys = []
		keys.append( key )
		if len( keys )> 100:
			keys = keys[ -100: ]
		current["skeys"] = keys
		current.markChanged()
	return( key )
	
def validateSecurityKey( key, isLongTermKey=False ):
	""" Validates a onetime securitykey for the current session
	
	@type key: String
	@param key: The key to validate
	@param isLongTermKey: Must be true, if the key was created with a fixed validationtime ,false otherwise
	@returns: If not isLongTermKey: True on success, False otherwise. If isLongTermKey, the stored data will be returned as dict on success
	"""
	if isLongTermKey:
		dbObj = db.Query("viur_security_keys" ).filter( "skey =", key ).get()
		if dbObj:
			res ={}
			for k in dbObj.keys():
				res[ k ] = dbObj[ k ]
			db.Delete( dbObj.key() )
			return( res )
	else:
		return( True )
		keys = current.get( "skeys" )
		if keys and key in keys:
			keys.remove( key )
			current["skeys"] = keys
			current.markChanged()
		return( True )
	return( False )
	
def sendEMail( dests, name , skel, extraFiles=[] ):
	"""Sends an EMail
	
	@type dests: String or [String]
	@param dests: EMail-Address (or list of Addresses) to send the mail to
	@type name: String
	@param name: Template (as String) or the filename to a template
	@type skel: Skeleton or Dict or None
	@param skel: Data made avaiable to the template. In case of a Skeleton it's parsed the usual way; Dictionarys are passed unchanged
	@type extraFiles: [open fileobjects]
	@param extraFiles: List of fileobjects to send within the mail as attachments
	"""
	from server import conf
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
	#container['Date'] = datetime.today().strftime("%a, %d %b %Y %H:%M:%S %z")
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
	message.sender = mailfrom
	message.html = data.encode('ascii', 'xmlcharrefreplace')
	if len( extraFiles )> 0:
		message.attachments = extraFiles
	message.send( )

def sendEMailToAdmins( subject, body, sender=None ):
	"""
		Sends an email to all admins of the current application. 
		(all users having access to the applications dashboard)
		
		@param subject: Subject of the message
		@type subject: string
		@param body: Message Body
		@type body: string
		@param sender: (optional) specify a differend sender
		@type sender: string
	"""
	if not sender:
		sender = "viur@%s.appspotmail.com" % app_identity.get_application_id()
	mail.send_mail_to_admins( sender, "=?utf-8?B?%s?=" % base64.b64encode( subject.encode("UTF-8") ), body.encode('ascii', 'xmlcharrefreplace') )

def getCurrentUser( ):
	"""
		Helper which returns the current user for the current request (if any)
	"""
	user = None
	if "user" in dir( conf["viur.mainApp"] ): #Check for our custom user-api
		user = conf["viur.mainApp"].user.getCurrentUser()
	return( user )

def markFileForDeletion( dlkey ):
	"""
	Adds a marker to the DB that the file might can be deleted.
	Once the mark has been set, the db is checked four times (default: every 4 hours)
	if the file is in use anywhere. If it is, the mark gets deleted, otherwise
	the mark and the file are removed from the DB. These delayed checks are necessary
	due to database inconsistency.
	
	@type dlkey: String
	@param dlkey: Downloadkey of the file
	"""
	fileObj = db.Query( "viur-deleted-files" ).filter( "dlkey", dlkey ).get()
	if fileObj: #Its allready marked
		return
	fileObj = db.Entity( "viur-deleted-files" )
	fileObj["itercount"] = 0
	fileObj["dlkey"] = str( dlkey )
	db.Put( fileObj )


