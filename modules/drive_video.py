__author__ = 'stefan'

import logging, pprint
from server.skeleton import Skeleton
from server.bones import stringBone
from server.applications.list import List
from server.tasks import StartupTask

from server.utils import get_stored_videos, get_credentials, retrieve_all_files, findVideoFolder, createFolder, build_service, add_local_video

class DriveVideoSkel(Skeleton):
	kindName = "drivevideo"
	searchIndex = "drivevideo"

	file_id = stringBone(descr="File Id in Google Drive (Do not change this unless you know what you're doing)",
	                     readOnly=False, required=True, indexed=True, searchable=True)
	title = stringBone(descr="Video Title", required=True, indexed=True, searchable=True)
	caption = stringBone(descr="Video Caption", required=False, indexed=True, searchable=True)
	preview_image_url = stringBone(descr="Thumbnail Bild URL von Google", required=False, indexed=True, searchable=True)


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

	# def push_notification(self, ):

# @StartupTask
def sync_with_drive():
	"""
		Syncs this appengine with drive content
	"""

	# try:
	by_id, by_file_id = get_stored_videos()
	print "by_id", repr(by_id.keys())
	print "by_file_id", repr(by_file_id.keys())
	for file_id, video in by_file_id.items():
		print file_id, video["caption"].value

	credentials = get_credentials()
	drive_service = build_service(credentials)
	folder_title = "videos"
	filelist = retrieve_all_files(drive_service)
	video_folder = findVideoFolder(filelist, folder_title)
	if not video_folder:
		video_folder = createFolder(drive_service, folder_title)

	if not video_folder:
		logging.critical("did not have an video folder in google drive. check the credentials...")

	remote_videos = retrieve_all_files(drive_service, video_folder["id"])

	remote_file_ids = dict()

	for remote_video in remote_videos:
		print
		pprint.pprint(remote_video)
		print
		if (u'explicitlyTrashed' not in remote_video or not remote_video[u'explicitlyTrashed']) and remote_video[u'mimeType'] != u'application/vnd.google-apps.folder' and remote_video["id"] not in by_file_id:
			local_video = add_local_video(remote_video)
			# by_id[local_video["id"]] = local_video
			# by_file_id[local_video["file_id"]] = local_video
			remote_file_ids[str(remote_video["id"])] = remote_video

	# print("remote_file_ids", repr(remote_file_ids.keys()))
	# for file_id, local_file in by_file_id.items():
	# 	if file_id not in remote_file_ids:
	# 		local_file["file_id"].value = "deleted"
	# 		local_file.toDB()

	# except Exception, err:
	# 	logging.debug(err)
