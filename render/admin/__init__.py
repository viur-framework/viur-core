# -*- coding: utf-8 -*-

from server.render.json.default import DefaultRender as default
from server.render.json.user import UserRender as user
from server.render.json.file import FileRender as file
from server.skeleton import Skeleton
from server import conf
from server import securitykey
from server import utils
from server import request
import datetime, json

__all__=[ default ]

def genSkey( *args,  **kwargs ):
	return json.dumps( securitykey.create() ) 
genSkey.exposed=True

def timestamp( *args, **kwargs):
	d = datetime.datetime.now()
	return( json.dumps( d.strftime("%Y-%m-%dT%H-%M-%S") ) )
timestamp.exposed=True

def getStructure( adminTree, modul ):
	if not modul in dir( adminTree ) \
	  or not "adminInfo" in dir( getattr( adminTree, modul ) )\
	  or not getattr( adminTree, modul ).adminInfo: 
		# Modul not known or no adminInfo for that modul
		return( json.dumps( None ) )
	res = {}
	try:
		modulObj = getattr( adminTree, modul )
	except:
		return( None )
	for stype in ["viewSkel","editSkel","addSkel", "viewLeafSkel", "viewNodeSkel", "editNodeSkel", "editLeafSkel", "addNodeSkel", "addLeafSkel"]: #Unknown skel type
		if stype in dir( modulObj ):
			try:
				skel = getattr( modulObj, stype )()
			except:
				continue
			if isinstance( skel, Skeleton ):
				res[ stype ] = default().renderSkelStructure( skel )
	if res:
		return( json.dumps( res ) )
	else:
		return( json.dumps( None ) )
	

def generateAdminConfig( adminTree ):
	res = {}
	for key in dir( adminTree ):
		app = getattr( adminTree, key )
		if "adminInfo" in dir( app ) and app.adminInfo:
			res[ key ] = app.adminInfo.copy()
			res[ key ]["name"] = _(res[ key ]["name"])
			res[ key ]["views"] = []
			if "views" in app.adminInfo.keys():
				for v in app.adminInfo["views"]:
					tmp = v.copy()
					tmp["name"] = _(tmp["name"])
					res[ key ]["views"].append( tmp )
	return( res )
	
def dumpConfig( adminTree ):
	adminConfig = generateAdminConfig( adminTree )
	res = {	"capabilities": conf["viur.capabilities"], 
			"modules": adminConfig, 
			"configuration": {}
		}
	for k, v in conf.items():
		if k.lower().startswith("admin."):
			res["configuration"][ k[ 6: ] ] = v
	return json.dumps( res )

def canAccess( *args, **kwargs ):
	user = utils.getCurrentUser()
	if user and "root" in user["access"]:
		return( True )
	pathList = request.current.get().pathlist
	if len( pathList )>=2 and pathList[1] == "skey":
		# Give the user the chance to login :)
		return( True )
	if len( pathList )>=3 and pathList[1] == "user" and (pathList[2] == "login" or pathList[2] == "getAuthMethod"):
		# Give the user the chance to login :)
		return( True )
	return( False )

def _postProcessAppObj( obj ):
	obj.skey = genSkey
	obj.timestamp = timestamp
	obj.config = lambda *args, **kwargs: dumpConfig( obj )
	obj.config.exposed=True
	obj.getStructure = lambda *args, **kwargs: getStructure( obj, *args, **kwargs )
	obj.getStructure.exposed = True
	obj.canAccess = canAccess
	return obj
