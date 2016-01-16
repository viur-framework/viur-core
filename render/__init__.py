# -*- coding: utf-8 -*-

from server.render.json.default import DefaultRender as default
from server.render.json.user import UserRender as user
from server.render.json.file import FileRender as file
from server.skeleton import Skeleton
from server import conf
from server import securitykey
from server import utils
from server import request
from server import session
import datetime, json

__all__=[ default ]

def genSkey( *args,  **kwargs ):
	return json.dumps( securitykey.create() ) 
genSkey.exposed=True

def timestamp( *args, **kwargs):
	d = datetime.datetime.now()
	return( json.dumps( d.strftime("%Y-%m-%dT%H-%M-%S") ) )
timestamp.exposed=True

def getStructure( adminTree, module ):
	if not module in dir( adminTree ) \
	  or not "adminInfo" in dir( getattr( adminTree, module ) )\
	  or not getattr( adminTree, module ).adminInfo:
		# Module not known or no adminInfo for that module
		return( json.dumps( None ) )
	res = {}
	try:
		moduleObj = getattr( adminTree, module )
	except:
		return( None )
	for stype in ["viewSkel","editSkel","addSkel", "viewLeafSkel", "viewNodeSkel", "editNodeSkel", "editLeafSkel", "addNodeSkel", "addLeafSkel"]: #Unknown skel type
		if stype in dir( moduleObj ):
			try:
				skel = getattr( moduleObj, stype )()
			except:
				continue
			if isinstance( skel, Skeleton ):
				res[ stype ] = default().renderSkelStructure( skel )
	if res:
		return( json.dumps( res ) )
	else:
		return( json.dumps( None ) )


def setLanguage( lang, skey):
	if not securitykey.validate( skey ):
		return( )
	if lang in conf["viur.avaiableLanguages"]:
		session.current.setLanguage( lang )
	return( )
setLanguage.exposed=True


def dumpConfig( adminTree ):
	adminConfig = {}
	for key in dir( adminTree ):
		app = getattr( adminTree, key )
		if "adminInfo" in dir( app ) and app.adminInfo:
			if callable( app.adminInfo ):
				info = app.adminInfo()
				if info is not None:
					adminConfig[ key ] = info
			else:
				adminConfig[ key ] = app.adminInfo.copy()
				adminConfig[ key ]["name"] = _(adminConfig[ key ]["name"])
				adminConfig[ key ]["views"] = []
				if "views" in app.adminInfo.keys():
					for v in app.adminInfo["views"]:
						tmp = v.copy()
						tmp["name"] = _(tmp["name"])
						adminConfig[ key ]["views"].append( tmp )
	res = {	"capabilities": conf["viur.capabilities"],
		"modules": adminConfig,
		"configuration": {}
		}
	for k, v in conf.items():
		if k.lower().startswith("admin."):
			res["configuration"][ k[ 6: ] ] = v

	if "viur.defaultlangs" in conf:
			res["viur.defaultlangs"] = conf["viur.defaultlangs"]
	if "viur.defaultlangsvalues" in conf:
		res["viur.defaultlangsvalues"] = conf["viur.defaultlangsvalues"]
	return json.dumps( res )

def canAccess( *args, **kwargs ):
	user = utils.getCurrentUser()
	if user and ("root" in user["access"] or "admin" in user["access"]):
		return( True )
	pathList = request.current.get().pathlist
	if len( pathList )>=2 and pathList[1] == "skey":
		# Give the user the chance to login :)
		return( True )
	if len( pathList )>=3 and pathList[1] == "user" and (pathList[2].startswith("auth_") or pathList[2].startswith("f2_") or pathList[2] == "getAuthMethod") or pathList[1] == "user" and pathList[2].startswith("login"):
		# Give the user the chance to login :)
		logging.error("TEST TRUE !")
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
	obj.setLanguage = setLanguage
	return obj
