# -*- coding: utf-8 -*-

from server.render.vi.default import DefaultRender as default
from server.render.vi.user import UserRender as user
from server.render.json.file import FileRender as file
from server.skeleton import Skeleton
from google.appengine.api import app_identity
from server import conf
from server import securitykey
from server import utils
from server import request
from server import session
from server import errors
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
		return

	if lang in conf["viur.availableLanguages"]:
		session.current.setLanguage( lang )

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
	return json.dumps( res )

def getVersion(*args, **kwargs):
	# We force the patch-level of our version to be always zero for security reasons
	return json.dumps((conf["viur.version"][0], conf["viur.version"][1], 0))
getVersion.exposed=True

def canAccess( *args, **kwargs ):
	user = utils.getCurrentUser()
	if user and ("root" in user["access"] or "admin" in user["access"]):
		return True

	pathList = request.current.get().pathlist

	if len( pathList ) >= 2 and pathList[1] in ["skey", "getVersion"]:
		# Give the user the chance to login :)
		return True

	if (len( pathList ) >= 3
	    and pathList[1] == "user"
	    and (pathList[2].startswith("auth_")
	            or pathList[2].startswith("f2_")
	            or pathList[2] == "getAuthMethods"
	            or pathList[2] == "logout")):

		# Give the user the chance to login :)
		return True

	if (len(pathList) >= 4
	    and pathList[1] == "user"
	    and pathList[2] == "view"
	    and pathList[3] == "self"):
		# Give the user the chance to view himself.
		return True

	return False

def index(*args, **kwargs):
	if request.current.get().isDevServer or request.current.get().isSSLConnection:
		raise errors.Redirect("/vi/s/main.html")
	else:
		appVersion = app_identity.get_default_version_hostname()
		raise errors.Redirect("https://%s/vi/s/main.html" % appVersion)

index.exposed=True

def _postProcessAppObj( obj ):
	obj.skey = genSkey
	obj.timestamp = timestamp
	obj.config = lambda *args, **kwargs: dumpConfig( obj )
	obj.config.exposed=True
	obj.getStructure = lambda *args, **kwargs: getStructure( obj, *args, **kwargs )
	obj.getStructure.exposed = True
	obj.canAccess = canAccess
	obj.setLanguage = setLanguage
	obj.getVersion = getVersion
	obj.index = index
	return obj
