# -*- coding: utf-8 -*-

from .default import DefaultRender as default
from .user import UserRender as user
from .file import FileRender as file
from server.utils import createSecurityKey
import json

__all__=[ default ]

def skey( *args,  **kwargs ):
	return json.dumps( createSecurityKey() ) 
skey.exposed=True


def _postProcessAppObj( obj ): #Register our SKey function
	obj.skey = skey
	return obj
