# -*- coding: utf-8 -*-

from .default import DefaultRender as default, serializeXML
from .user import UserRender as user
from .file import FileRender as file
from server import conf
from server.utils import createSecurityKey
import datetime


__all__=[ default ]

def skey( *args,  **kwargs ):
	return json.dumps( createSecurityKey() ) 
skey.exposed=True

def timestamp( *args, **kwargs):
	d = datetime.datetime.now()
	return( serializeXML( d.strftime("%Y-%m-%dT%H-%M-%S") ) )
timestamp.exposed=True

def generateAdminConfig( adminTree ):
	res = {}
	for key in dir( adminTree ):
		app = getattr( adminTree, key )
		if "adminInfo" in dir( app ) and app.adminInfo:
			res[ key ] = app.adminInfo
	return( res )
	
def dumpConfig( adminConfig ):
	return serializeXML( {
		"capabilities": conf["viur.capabilities"], 
		"modules": adminConfig
		} )

def _postProcessAppObj( obj ):
	obj.skey = skey
	obj.timestamp = timestamp
	adminConfig = generateAdminConfig( obj )
	tmp = lambda *args, **kwargs: dumpConfig( adminConfig )
	tmp.exposed=True
	obj.config = tmp
	return obj
