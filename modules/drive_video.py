__author__ = 'stefan'

import logging
import httplib2

from server.tasks import PeriodicTask
from server.skeleton import Skeleton
from server.bones import stringBone, fileBone
from server.applications.list import List
from server.tasks import StartupTask
from oauth2client.client import Credentials
from apiclient.discovery import build
from apiclient import errors
from server.config import conf


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
			logging.exception(error)
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
	video_module = getattr(conf["viur.mainApp"], "drivevideos")
	skellist = video_module.viewSkel().all().fetch()
	by_id = dict()
	by_file_id = dict()
	for video in skellist:
		by_file_id[str(video["file_id"].value)] = video
		by_id[str(video["id"].value)] = video
	return by_id, by_file_id


def add_local_video(video):
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


# utils

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


def parseChangeList(service, changelist, local_videos, video_folder):
	for change in changelist:
		# logging.debug("parseChangeList:: change item %r", change)
		if change["kind"] == "drive#change":
			if "deleted" == True:
				try:
					local_video = local_videos["fileId"]
					local_video.delete()
					logging.debug(
						"locally deleted a drivevideos entry since it's referenced media was removed from drive:",
						fileobj)
				except KeyError:
					logging.debug("parseChangeList:: deleted unknown video %r", change["fileId"])
			elif "file" in change:
				fileobj = change["file"]
				for parent in fileobj["parents"]:
					if parent["id"] == video_folder["id"]:
						if fileobj["createdDate"] == fileobj["modifiedDate"]:
							logging.debug("File created:", fileobj)
							add_local_video(fileobj)
						elif change["deleted"]:
							logging.debug("File deleted:", fileobj)
						else:
							logging.debug("other change kind:", fileobj)


def get_local_videos():
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


# end utils

class DriveVideoSkel(Skeleton):
	kindName = "drivevideo"
	searchIndex = "drivevideo"

	file_id = stringBone(descr="File Id in Google Drive (Do not change this unless you know what you're doing)",
	                     readOnly=False, required=True, indexed=True, searchable=True)
	title = stringBone(descr="Video Title", required=True, indexed=True, searchable=True)
	caption = stringBone(descr="Video Caption", required=False, indexed=True, searchable=True)
	preview_image_url = stringBone(descr="Thumbnail Bild URL von Google", required=False, indexed=True, searchable=True)
	thumbnail_image = fileBone(descr=u"Thumbnail Bild", required=False, multiple=False,
	                           params={"frontend_list_visible": True})


class DriveVideoList(List):
	kindName = "drivevideo"
	listTemplate = "drive_video_list"
	viewTemplate = "drive_video_view"

	adminInfo = {"name": u"DriveVideos",  # Name of this modul, as shown in ViUR (will be translated at runtime)
	             "handler": "list",  # Which handler to invoke
	             "icon": "icons/modules/google_drive.svg",  # Icon for this modul
	             "filter": {"orderby": "name"},
	             "columns": ["id", "title", "caption", "file_id"],
	             "sortIndex": 50
	}

	def drive_changes(self):
		check_drive_modifications()
		return "OK"

	drive_changes.exposed = True


@PeriodicTask(60 * 4)
def check_drive_modifications():
	try:
		logging.debug("check_drive_modifications started")
		by_id, by_file_id = get_local_videos()

		credentials = get_credentials()
		drive_service = build_service(credentials)
		folder_title = "videos"
		filelist = retrieve_all_files(drive_service)
		logging.debug("check_drive_modifications:: filelist %r", filelist)
		video_folder = findVideoFolder(filelist, folder_title)
		if not video_folder:
			video_folder = createFolder(drive_service, folder_title)

		changes = retrieve_all_changes(drive_service)
		logging.debug("check_drive_modifications:: changelist raw %r", changes)
		parseChangeList(drive_service, changes, by_file_id, video_folder)

	except Exception, err:
		logging.exception(err)
	finally:
		logging.debug("check_drive_modifications finished")


# @StartupTask
def sync_with_drive():
	"""
			Syncs this appengine with drive content
	"""

	try:
		by_id, by_file_id = get_local_videos()

		credentials = get_credentials()
		drive_service = build_service(credentials)
		folder_title = "videos"
		filelist = retrieve_all_files(drive_service)
		video_folder = findVideoFolder(filelist, folder_title)
		if not video_folder:
			video_folder = createFolder(drive_service, folder_title)

		if not video_folder:
			logging.critical("did not found a video folder in google drive. please recheck the credentials...")

		remote_videos = retrieve_all_files(drive_service, video_folder["id"])

		remote_file_ids = dict()

		for remote_video in remote_videos:
			if (u'explicitlyTrashed' not in remote_video or not remote_video[u'explicitlyTrashed']) and remote_video[
				u'mimeType'] != u'application/vnd.google-apps.folder':
				remote_file_ids[str(remote_video["id"])] = remote_video
				if remote_video["id"] not in by_file_id:
					local_video = add_local_video(remote_video)

		for file_id, local_file in by_file_id.items():
			if file_id not in remote_file_ids:
				local_file["file_id"].value = None
				local_file.delete()

	except Exception, err:
		logging.exception(err)
