__author__ = 'stefan'

from server.skeleton import Skeleton
from server.bones import stringBone
from server.applications.list import List


class DriveVideoSkel(Skeleton):
	kindName = "drivevideo"
	searchIndex = "drivevideo"

	file_id = stringBone(descr="File Id by Google Drive", readOnly=False, required=True, indexed=True, searchable=True)
	title = stringBone(descr="Video Title")
	caption = stringBone(descr="Video Caption")


class DriveVideoList(List):
	kindName = "drivevideo"
	listTemplate = "drive_video_list"
	viewTemplate = "drive_video_view"

	adminInfo = {"name": u"DriveVideos",  # Name of this modul, as shown in ViUR (will be translated at runtime)
	             "handler": "list",  #Which handler to invoke
	             "icon": "icons/modules/google_drive.svg",  #Icon for this modul
	             "filter": {"orderby": "name"},
	             "columns": ["id", "title", "caption"],
	             "sortIndex": 50
	}
