# -*- coding: utf-8 -*-
import json
import urllib.parse
import urllib.request

from viur.core import request, utils
from viur.core.bones import bone
from viur.core.bones.bone import ReadFromClientError, ReadFromClientErrorSeverity


class captchaBone(bone.baseBone):
	type = "captcha"

	def __init__(self, publicKey=None, privateKey=None, *args, **kwargs):
		bone.baseBone.__init__(self, *args, **kwargs)
		self.defaultValue = self.publicKey = publicKey
		self.privateKey = privateKey
		self.required = True
		self.hasDBField = False

	def serialize(self, skel, name) -> bool:
		return False

	def unserialize(self, skel, name) -> bool:
		skel.accessedValues[name] = self.publicKey
		return True

	def fromClient(self, skel, name, data):
		"""
			Reads a value from the client.
			If this value is valid for this bone,
			store this value and return None.
			Otherwise our previous value is
			left unchanged and an error-message
			is returned.

			:param name: Our name in the skeleton
			:type name: str
			:param data: *User-supplied* request-data
			:type data: dict
			:returns: None or String
		"""
		if request.current.get().isDevServer:  # We dont enforce captchas on dev server
			return None
		user = utils.getCurrentUser()
		if user and "root" in user["access"]:
			return None  # Don't bother trusted users with this (not supported by admin/vi anyways)

		if not "g-recaptcha-response" in data:
			return [ReadFromClientError(ReadFromClientErrorSeverity.NotSet, name, "No Captcha given!")]

		data = {
			"secret": self.privateKey,
			"remoteip": request.current.get().request.remote_addr,
			"response": data["g-recaptcha-response"]
		}

		req = urllib.request.Request(url="https://www.google.com/recaptcha/api/siteverify",
									 data=urllib.parse.urlencode(data).encode(),
									 method="POST")
		response = urllib.request.urlopen(req)

		if json.loads(response.read()).get("success"):
			return None

		return [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, name, "Invalid Captcha")]
