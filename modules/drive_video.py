# -*- coding: utf-8 -*-
import logging

import httplib2
from oauth2client.client import Credentials
from apiclient.discovery import build
from apiclient import errors

# from server.tasks import PeriodicTask
from server.skeleton import Skeleton
from server.bones import stringBone, fileBone
from server.applications.list import List
from server.config import conf
from server import errors as server_errors


class DriveVideoList(List):
	kindName = "drivevideo"
	listTemplate = "drive_video_list"
	viewTemplate = "drive_video_view"

	adminInfo = {
		"name": u"DriveVideos",  # Name of this module, as shown in ViUR (will be translated at runtime)
		"handler": "list",  # Which handler to invoke
		"icon": "icons/modules/google_drive.svg",  # Icon for this module
		"filter": {"orderby": "name"},
		"columns": ["id", "title", "caption", "file_id"],
		"sortIndex": 50
	}

	def drive_changes(self, *args, **kwars):
		if not self.canAdd():
			raise server_errors.Unauthorized()
		sync_with_drive()
		return "OK"

	drive_changes.exposed = True


class DriveVideoSkel(Skeleton):
	kindName = "drivevideo"
	searchIndex = "drivevideo"

	file_id = stringBone(
		descr=u"File Id in Google Drive (Do not change this unless you know what you're doing)",
		readOnly=False,
		required=True,
		indexed=True,
		searchable=True
	)
	title = stringBone(
		descr=u"Video Title",
		required=True,
		indexed=True,
		searchable=True
	)
	caption = stringBone(
		descr=u"Video Caption",
		required=False,
		indexed=True,
		searchable=True
	)
	preview_image_url = stringBone(
		descr=u"Thumbnail Bild URL von Google",
		required=False,
		indexed=True,
		searchable=True
	)
	thumbnail_image = fileBone(
		descr=u"Thumbnail Bild",
		required=False,
		multiple=False,
		params={"frontend_list_visible": True}
	)


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


def retrieve_all_files(service, folder_id='root'):
	"""Retrieve a list of File resources.

	  Args:
		service: Drive API service instance.
	  Returns:
		List of File resources.
	  """
	result = []
	page_token = None
	while True:
		param = dict()
		if page_token:
			param['pageToken'] = page_token
		children = service.children().list(folderId=folder_id, **param).execute()
		for child in children.get("items", []):
			fileobj = service.files().get(fileId=child["id"]).execute()
			result.append(fileobj)
		page_token = children.get('nextPageToken')
		if not page_token:
			break
	return result


def find_video_folder(filelist, folder_title="videos"):
	for item in filelist:
		if (u'explicitlyTrashed' not in item or not item[u'explicitlyTrashed']) and "mimeType" in item and item[
			"mimeType"] == "application/vnd.google-apps.folder" and item[
			"title"] == folder_title:
			return item

	return None


def create_folder(service, parent_id='root', folder_title="videos"):
	body = {
	'parent': parent_id,
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
			logging.exception(error)
			break
	return result


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


def parse_change_list(service, changelist, local_videos, video_folder):
	for change in changelist:
		# logging.debug("parse_change_list:: change item %r", change)
		if change["kind"] == "drive#change":
			if change["deleted"]:
				try:
					local_video = local_videos["fileId"]
					local_video.delete()
					logging.debug(
						"locally deleted a drivevideos entry since it's referenced media was removed from drive:",
						change)
				except KeyError:
					logging.debug("parse_change_list:: deleted unknown video %r", change["fileId"])
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
	video_module = getattr(conf["viur.mainApp"], "drivevideos")
	skellist = video_module.viewSkel().all().fetch(99)
	by_id = dict()
	by_file_id = dict()
	for video in skellist:
		by_file_id[str(video["file_id"].value)] = video
		by_id[str(video["id"].value)] = video
	return by_id, by_file_id


# TODO: periodic task should be recursively deferred for each subfolder, don't use this for now
# @PeriodicTask(60 * 4)
def check_drive_modifications():
	raise Exception()
	try:
		logging.debug("check_drive_modifications started")
		by_id, by_file_id = get_local_videos()

		credentials = get_credentials()
		drive_service = build_service(credentials)
		folder_title = "videos"
		filelist = retrieve_all_files(drive_service)
		logging.debug("check_drive_modifications:: filelist %r", filelist)
		video_folder = find_video_folder(filelist, folder_title)
		if not video_folder:
			video_folder = create_folder(drive_service, folder_title)

		changes = retrieve_all_changes(drive_service)
		logging.debug("check_drive_modifications:: changelist raw %r", changes)
		parse_change_list(drive_service, changes, by_file_id, video_folder)

	except Exception, err:
		logging.exception(err)
	finally:
		logging.debug("check_drive_modifications finished")


def get_all_files(service, remote_files):
	result = list()
	for remote_object in remote_files:
		if (u'explicitlyTrashed' not in remote_object or not remote_object[
			u'explicitlyTrashed']) and "mimeType" in remote_object and remote_object[
			"mimeType"] == "application/vnd.google-apps.folder":
			child_objects = retrieve_all_files(service, remote_object["id"])
			result.extend(get_all_files(service, child_objects))
		else:
			result.append(remote_object)
	return result


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
		video_folder = find_video_folder(filelist, folder_title)

		if not video_folder:
			logging.critical("did not found a 'videos' directory in google drive. please create it by hand...")
			return

		remote_objects = retrieve_all_files(drive_service, video_folder["id"])
		remote_objects = get_all_files(drive_service, remote_objects)
		remote_file_ids = dict()

		for remote_file in remote_objects:
			if u'explicitlyTrashed' not in remote_file or not remote_file[u'explicitlyTrashed']:
				remote_file_ids[str(remote_file["id"])] = remote_file
				if remote_file["id"] not in by_file_id:
					add_local_video(remote_file)

		for file_id, local_file in by_file_id.items():
			if file_id not in remote_file_ids:
				local_file["file_id"].value = None
				local_file.delete()

	except Exception, err:
		logging.exception(err)
