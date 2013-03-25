# -*- coding: utf-8 -*-
from server.config import sharedConf
from time import sleep
from server import db, request

currentVersion = 1

def markFileRefsStrong():
	"""Adds the weak=False marker to all Filerefs without such an marker"""
	for file in db.Query( "file" ).iter():
		if not "weak" in file.keys():
			file["weak"] = False
			db.Put( file )

#List Updatescripts here: old-Version -> [List of Scripts]
updateScripts = {	0: [markFileRefsStrong]
				}

def checkUpdate():
	if sharedConf["viur.apiVersion"]<currentVersion:
		#Put all instances on Hold
		sharedConf["viur.disabled"] = True
		if not request.current.get().isDevServer:
			# Sleep only on live instances - theres no race-contition locally
			sleep( sharedConf.updateInterval.seconds+30 )
		for version in range( int(sharedConf["viur.apiVersion"]), currentVersion ):
			if version in updateScripts.keys():
				for script in updateScripts[ version ]:
					script()
		sharedConf["viur.disabled"] = False #Reenable Apps
		sharedConf["viur.apiVersion"] = currentVersion
	
