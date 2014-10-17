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
					logging.debug("locally deleted a drivevideos entry since it's referenced media was removed from drive:", fileobj)
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
	thumbnail_image = fileBone(descr=u"Thumbnail Bild", required=False, multiple=False, params={"frontend_list_visible": True})


class DriveVideoList(List):
	kindName = "drivevideo"
	listTemplate = "drive_video_list"
	viewTemplate = "drive_video_view"

	adminInfo = {"name": u"DriveVideos",  # Name of this modul, as shown in ViUR (will be translated at runtime)
	             "handler": "list",  # Which handler to invoke
	             "icon": "icons/modules/google_drive.svg",  #Icon for this modul
	             "filter": {"orderby": "name"},
	             "columns": ["id", "title", "caption", "file_id"],
	             "sortIndex": 50
	}

	def drive_changes(self):
		check_drive_modifications()
		return "OK"
	drive_changes.exposed=True


	# def push_notification(self, ):


change_list = [{u'id': u'5192', u'fileId': u'1Gw7YPYgMgNNU42skibULbJJUx_suP_CpjSEdSi8_z9U',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/5192',
                u'modificationDate': u'2014-01-13T18:26:04.341Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'5662', u'fileId': u'1N3XyVkAP8nmWjASz8L_OjjnjVKxgeVBjIsTr5qIUcA4',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/5662',
                u'modificationDate': u'2014-06-22T23:36:28.994Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'6194', u'fileId': u'0B8EFkKLyh8FWZ3NlaVlLTm9ubG8',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6194',
                u'modificationDate': u'2014-10-07T18:09:55.744Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'6196', u'fileId': u'0B8EFkKLyh8FWYm1IX1NpRjd0QUk',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6196',
                u'modificationDate': u'2014-10-07T18:09:55.744Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'6198', u'fileId': u'0B8EFkKLyh8FWOXlVaUdQS2hXcDg',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6198',
                u'modificationDate': u'2014-10-07T18:09:55.744Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'6203', u'fileId': u'0B8EFkKLyh8FWTDZvTm44b2Z6bE0',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6203',
                u'modificationDate': u'2014-10-07T18:09:55.744Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'6205', u'fileId': u'0B8EFkKLyh8FWWmJMMUJZMXZmUlk',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6205',
                u'modificationDate': u'2014-10-07T18:09:55.744Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'6207', u'fileId': u'0B8EFkKLyh8FWMWFRbzRyOE9OTjQ',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6207',
                u'modificationDate': u'2014-10-07T18:09:55.744Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'6214', u'fileId': u'0B8EFkKLyh8FWUnRWeWhRNGE3UjQ',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6214',
                u'modificationDate': u'2014-10-07T18:09:58.276Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'6217', u'fileId': u'0B8EFkKLyh8FWdm5DT01icWRxTFk',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6217',
                u'modificationDate': u'2014-10-07T18:09:58.276Z', u'kind': u'drive#change', u'deleted': True},
               {u'id': u'6268',
                u'file': {u'etag': u'"ysueZUkrDgRXGY22AYAOH6Xl_qU/MTQxMjk0NDQyMDMyMw"', u'mimeType': u'video/mp4',
                          u'userPermission': {u'etag': u'"ysueZUkrDgRXGY22AYAOH6Xl_qU/OCSdJHcYDg1R_rJtWM1dItsG6NM"',
                                              u'id': u'me', u'role': u'owner',
                                              u'selfLink': u'https://www.googleapis.com/drive/v2/files/0B8EFkKLyh8FWZktBRm5hMXB5Sk0/permissions/me',
                                              u'kind': u'drive#permission', u'type': u'user'},
                          u'labels': {u'hidden': False, u'viewed': True, u'starred': False, u'restricted': False,
                                      u'trashed': False},
                          u'headRevisionId': u'0B8EFkKLyh8FWSU9hc1FoWFpFaTE0Sm9GYS85VjJBbXErcmlVPQ',
                          u'modifiedDate': u'2014-10-10T12:33:40.323Z', u'shared': True,
                          u'originalFilename': u'TestVideo.mp4', u'fileSize': u'540689',
                          u'md5Checksum': u'44be3fcf7f69159bd35da23af8917a68', u'version': u'6267',
                          u'embedLink': u'https://video.google.com/get_player?ps=docs&partnerid=30&docid=0B8EFkKLyh8FWZktBRm5hMXB5Sk0&BASE_URL=http://docs.google.com/',
                          u'alternateLink': u'https://docs.google.com/file/d/0B8EFkKLyh8FWZktBRm5hMXB5Sk0/edit?usp=drivesdk',
                          u'fileExtension': u'mp4', u'createdDate': u'2014-10-06T14:47:03.126Z',
                          u'writersCanShare': True, u'owners': [
	                {u'kind': u'drive#user', u'permissionId': u'09637875450328902433',
	                 u'displayName': u'Stefan K\xf6gl', u'emailAddress': u'stkoeg@gmail.com',
	                 u'isAuthenticatedUser': True}], u'modifiedByMeDate': u'2014-10-10T12:33:40.323Z',
                          u'id': u'0B8EFkKLyh8FWZktBRm5hMXB5Sk0', u'appDataContents': False,
                          u'thumbnailLink': u'https://lh6.googleusercontent.com/8uY8b1w1T64M1k83jhbOmRPwITPGsmjDdDOmPrh-1hfiTN1WnCt5G7qfsKGmGGxHB68u1g=s220',
                          u'lastModifyingUser': {u'kind': u'drive#user', u'permissionId': u'09637875450328902433',
                                                 u'displayName': u'Stefan K\xf6gl',
                                                 u'emailAddress': u'stkoeg@gmail.com', u'isAuthenticatedUser': True},
                          u'selfLink': u'https://www.googleapis.com/drive/v2/files/0B8EFkKLyh8FWZktBRm5hMXB5Sk0',
                          u'lastViewedByMeDate': u'2014-10-10T12:31:22.978Z', u'editable': True,
                          u'title': u'TestVideo.mp4', u'copyable': True, u'quotaBytesUsed': u'540689',
                          u'ownerNames': [u'Stefan K\xf6gl'], u'parents': [{u'kind': u'drive#parentReference',
                                                                            u'parentLink': u'https://www.googleapis.com/drive/v2/files/0B8EFkKLyh8FWTHNoVEhkZDJCNDg',
                                                                            u'isRoot': False,
                                                                            u'selfLink': u'https://www.googleapis.com/drive/v2/files/0B8EFkKLyh8FWZktBRm5hMXB5Sk0/parents/0B8EFkKLyh8FWTHNoVEhkZDJCNDg',
                                                                            u'id': u'0B8EFkKLyh8FWTHNoVEhkZDJCNDg'}],
                          u'downloadUrl': u'https://doc-10-10-docs.googleusercontent.com/docs/securesc/2jpv0gjru2p55f4luqmnrlb04daqlsbo/lge4pg9nram678a31unqtk3f776asat2/1413352800000/13058876669334088843/09637875450328902433/0B8EFkKLyh8FWZktBRm5hMXB5Sk0?h=16653014193614665626&e=download&gd=true',
                          u'markedViewedByMeDate': u'2014-10-10T10:31:15.932Z',
                          u'iconLink': u'https://ssl.gstatic.com/docs/doclist/images/icon_11_video_list.png',
                          u'kind': u'drive#file',
                          u'webContentLink': u'https://docs.google.com/uc?id=0B8EFkKLyh8FWZktBRm5hMXB5Sk0&export=download',
                          u'lastModifyingUserName': u'Stefan K\xf6gl', u'description': u'Test Video Beschreibung\n'},
                u'fileId': u'0B8EFkKLyh8FWZktBRm5hMXB5Sk0',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6268',
                u'modificationDate': u'2014-10-10T12:33:40.516Z', u'kind': u'drive#change', u'deleted': False},
               {u'id': u'6282', u'file': {u'etag': u'"ysueZUkrDgRXGY22AYAOH6Xl_qU/MTQxMjg3OTY1NDIxMw"',
                                          u'mimeType': u'application/vnd.google-apps.folder', u'userPermission': {
               u'etag': u'"ysueZUkrDgRXGY22AYAOH6Xl_qU/st1JuM33WNsLn61gyhhbTcOHh0A"', u'id': u'me', u'role': u'owner',
               u'selfLink': u'https://www.googleapis.com/drive/v2/files/0B8EFkKLyh8FWTHNoVEhkZDJCNDg/permissions/me',
               u'kind': u'drive#permission', u'type': u'user'},
                                          u'labels': {u'hidden': False, u'viewed': True, u'starred': False,
                                                      u'restricted': False, u'trashed': False},
                                          u'modifiedDate': u'2014-10-09T18:34:14.213Z', u'shared': True,
                                          u'version': u'6281',
                                          u'alternateLink': u'https://docs.google.com/folderview?id=0B8EFkKLyh8FWTHNoVEhkZDJCNDg&usp=drivesdk',
                                          u'createdDate': u'2014-10-06T14:38:13.142Z', u'writersCanShare': True,
                                          u'owners': [{u'kind': u'drive#user', u'permissionId': u'09637875450328902433',
                                                       u'displayName': u'Stefan K\xf6gl',
                                                       u'emailAddress': u'stkoeg@gmail.com',
                                                       u'isAuthenticatedUser': True}],
                                          u'modifiedByMeDate': u'2014-10-06T17:35:27.171Z',
                                          u'id': u'0B8EFkKLyh8FWTHNoVEhkZDJCNDg', u'appDataContents': False,
                                          u'lastModifyingUser': {u'kind': u'drive#user',
                                                                 u'permissionId': u'09637875450328902433',
                                                                 u'displayName': u'Stefan K\xf6gl',
                                                                 u'emailAddress': u'stkoeg@gmail.com',
                                                                 u'isAuthenticatedUser': True},
                                          u'selfLink': u'https://www.googleapis.com/drive/v2/files/0B8EFkKLyh8FWTHNoVEhkZDJCNDg',
                                          u'lastViewedByMeDate': u'2014-10-12T10:26:08.790Z', u'editable': True,
                                          u'title': u'videos', u'copyable': False, u'quotaBytesUsed': u'0',
                                          u'webViewLink': u'https://86aa09aefea7d7bc4512afffb4382d8596a442ca.googledrive.com/host/0B8EFkKLyh8FWTHNoVEhkZDJCNDg/',
                                          u'ownerNames': [u'Stefan K\xf6gl'], u'parents': [
	               {u'kind': u'drive#parentReference',
	                u'parentLink': u'https://www.googleapis.com/drive/v2/files/0AMEFkKLyh8FWUk9PVA', u'isRoot': True,
	                u'selfLink': u'https://www.googleapis.com/drive/v2/files/0B8EFkKLyh8FWTHNoVEhkZDJCNDg/parents/0AMEFkKLyh8FWUk9PVA',
	                u'id': u'0AMEFkKLyh8FWUk9PVA'}], u'markedViewedByMeDate': u'2014-10-12T10:26:08.771Z',
                                          u'iconLink': u'https://ssl.gstatic.com/docs/doclist/images/icon_11_collection_list.png',
                                          u'kind': u'drive#file', u'lastModifyingUserName': u'Stefan K\xf6gl'},
                u'fileId': u'0B8EFkKLyh8FWTHNoVEhkZDJCNDg',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6282',
                u'modificationDate': u'2014-10-12T10:26:08.845Z', u'kind': u'drive#change', u'deleted': False},
               {u'id': u'6286', u'fileId': u'0B8EFkKLyh8FWaGR4eGNqUmE4SHc',
                u'selfLink': u'https://www.googleapis.com/drive/v2/changes/6286',
                u'modificationDate': u'2014-10-12T10:26:23.020Z', u'kind': u'drive#change', u'deleted': True}]


# @StartupTask
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
			if (u'explicitlyTrashed' not in remote_video or not remote_video[u'explicitlyTrashed']) and remote_video[u'mimeType'] != u'application/vnd.google-apps.folder':
				remote_file_ids[str(remote_video["id"])] = remote_video
				if remote_video["id"] not in by_file_id:
					local_video = add_local_video(remote_video)

		for file_id, local_file in by_file_id.items():
			if file_id not in remote_file_ids:
				local_file["file_id"].value = None
				local_file.delete()

	except Exception, err:
		logging.exception(err)
