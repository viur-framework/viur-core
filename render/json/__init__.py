# -*- coding: utf-8 -*-

from .default import DefaultRender as default
from .user import UserRender as user
from .file import FileRender as file
from server import securitykey
import json

__all__ = [default]


def genSkey(*args, **kwargs):
	return json.dumps(securitykey.create())


genSkey.exposed = True


def _postProcessAppObj(obj):  # Register our SKey function
	obj.skey = genSkey
	return obj
