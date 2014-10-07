# -*- coding: utf-8 -*-

import pprint
import httplib2

from oauth2client.client import Credentials
from apiclient.discovery import build
from apiclient import errors
from server import db
from server.config import conf

from google.appengine.api import memcache, app_identity, mail
from google.appengine.ext import deferred
import new, os
from server import db
import string, random, base64
from server.config import conf
import logging


def generateRandomString( length=13 ):
	"""Returns a new random String of the given length.
	Its safe to use this string in urls or html.
	
	@type length: Int
	@name length: Length of the generated String
	@return: A new random String of the given length
	"""
	return(  ''.join( [ random.choice(string.ascii_lowercase+string.ascii_uppercase + string.digits) for x in range(13) ] ) )

	
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
	message.html = data.replace("\x00","").encode('ascii', 'xmlcharrefreplace')
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


def get_credentials():
	cred_json_str = conf["video_credentials"]
	return Credentials.new_from_json(cred_json_str)


def set_credentials(credentials):
	conf["video_credentials"] = credentials


def build_service(credentials):
	"""Build a Drive service object.

	  Args:
		credentials: OAuth 2.0 credentials.

	  Returns:
		Drive service object.
	  """
	http = httplib2.Http()
	http = credentials.authorize(http)
	return build('drive', 'v2', http=http)


def retrieve_all_files(service, folderId='root'):
	"""Retrieve a list of File resources.

	  Args:
		service: Drive API service instance.
	  Returns:
		List of File resources.
	  """
	result = []
	page_token = None
	while True:
		try:
			param = dict()
			if page_token:
				param['pageToken'] = page_token
			children = service.children().list(folderId=folderId, **param).execute()
			for child in children.get("items", []):
				fileobj = service.files().get(fileId=child["id"]).execute()
				result.append(fileobj)

			page_token = children.get('nextPageToken')
			if not page_token:
				break
		except errors.HttpError, error:
			print 'An error occurred: %s' % error
			break
	return result


def findVideoFolder(filelist, folder_title="videos"):
	print "findVideoFolder", folder_title
	for item in filelist:
		# print
		# print "*" * 50
		# pprint.pprint(myfile)
		if "mimeType" in item and item["mimeType"] == "application/vnd.google-apps.folder" and item[
			"title"] == folder_title:
			return item

	return None


def createFolder(service, parentId='root', folder_title="videos"):
	print "createFolder", parentId, folder_title
	body = {
	'parent': parentId,
	'description': "used by viur server for embedded videos. Do not delete this folder unless you know what you're "
	               "doing!",
	'title': folder_title,
	'mimeType': "application/vnd.google-apps.folder"
	}
	video_folder = service.files().insert(body=body).execute()
	return video_folder


def retrieve_all_changes(service, start_change_id=None):
	"""Retrieve a list of Change resources.

	  Args:
		service: Drive API service instance.
		start_change_id: ID of the change to start retrieving subsequent changes
						 from or None.
	  Returns:
		List of Change resources.
	  """
	result = []
	page_token = None
	while True:
		try:
			param = {}
			if start_change_id:
				param['startChangeId'] = start_change_id
			if page_token:
				param['pageToken'] = page_token
			changes = service.changes().list(**param).execute()

			result.extend(changes['items'])
			page_token = changes.get('nextPageToken')
			if not page_token:
				break
		except errors.HttpError, error:
			print 'An error occurred: %s' % error
			break
	return result


def parseChangeList(service, changelist, video_folder):
	for change in changelist:
		if "file" in change:
			fileobj = change["file"]
			for parent in fileobj["parents"]:
				if parent["id"] == video_folder["id"]:
					if fileobj["createdDate"] == fileobj["modifiedDate"]:
						print
						print "File created:"
					elif change["deleted"]:
						print
						print "file deleted:"
					else:
						print
						print "file changed:"
					# pprint.pprint(fileobj)
					# print


def get_stored_videos():
	print("conf viur.mainapp", dir(conf["viur.mainApp"]))
	video_module = getattr(conf["viur.mainApp"], "drivevideos")
	skellist = video_module.viewSkel().all().fetch()
	by_id = dict()
	by_file_id = dict()
	for video in skellist:
		by_file_id[str(video["file_id"].value)] = video
		by_id[str(video["id"].value)] = video
	return by_id, by_file_id


def add_local_video(video):
	print "add local", type(video)
	print
	video_module = getattr(conf["viur.mainApp"], "drivevideos")
	skel = video_module.addSkel()
	skel["title"].value = video[u"title"]
	skel["file_id"].value = video[u"id"]
	try:
		skel["caption"].value = video["description"]
	except KeyError:
		pass
	skel.toDB()
	return skel
