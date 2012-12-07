# -*- coding: utf-8 -*-
from server.config import sharedConf
from time import sleep

currentVersion = 1

def markFileRefsStrong():
	"""Adds the weak=False marker to all Filerefs without such an marker"""
	from utils import generateExpandoClass
	fileClass = generateExpandoClass( "file" )
	for file in fileClass.query().iter():
		if not "weak" in file._properties.keys():
			file.weak = False
			file.put()

#List Updatescripts here: old-Version -> [List of Scripts]
updateScripts = {	0: [markFileRefsStrong]
				}

def checkUpdate():
	if sharedConf["viur.apiVersion"]<currentVersion:
		#Put all instances on Hold
		sharedConf["viur.disabled"] = True
		sleep( sharedConf.updateInterval.seconds+30 )
		for version in range( int(sharedConf["viur.apiVersion"]), currentVersion ):
			if version in updateScripts.keys():
				for script in updateScripts[ version ]:
					script()
		sharedConf["viur.disabled"] = False #Reenable Apps
		sharedConf["viur.apiVersion"] = currentVersion
	
