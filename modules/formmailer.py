# -*- coding: utf-8 -*-
from viur.core.skeleton import RelSkel
from viur.core import errors, utils, securitykey, exposed
from viur.core.bones import baseBone
from viur.core.prototypes.basic import BasicApplication


class MailSkel(RelSkel):
	changedate = None  # Changedates won't apply here


class Formmailer(BasicApplication):
	mailTemplate = None

	@exposed
	def index(self, *args, **kwargs):
		if not self.canUse():
			raise errors.Forbidden()  # Unauthorized

		skel = self.mailSkel()

		if len(kwargs) == 0:
			return self.render.add(skel=skel, failed=False)

		if not skel.fromClient(kwargs) or not "skey" in kwargs:
			return self.render.add(skel=skel, failed=True)

		if not securitykey.validate(kwargs["skey"], useSessionKey=True):
			raise errors.PreconditionFailed()

		# Allow bones to perform outstanding "magic" operations before sending the mail
		for key, _bone in skel.items():
			if isinstance(_bone, baseBone):
				_bone.performMagic(skel.valuesCache, key, isAdd=True)

		# Get recipients
		rcpts = self.getRcpts(skel)

		# Get additional options for sendEMail
		opts = self.getOptions(skel)
		if not isinstance(opts, dict):
			opts = {}

		# Send the email!
		utils.sendEMail(rcpts, self.mailTemplate, skel, **opts)
		self.onItemAdded(skel)

		return self.render.addItemSuccess(skel)

	@exposed
	def add(self, *args, **kwargs):
		return self.index(*args, **kwargs)

	def canUse(self):
		return False

	def mailSkel(self):
		raise NotImplementedError("You must implement the \"mailSkel\" function!")

	def getRcpts(self, skel):
		raise NotImplementedError("You must implement the \"getRcpts\" function!")

	def getOptions(self, skel):
		return None

	def onItemAdded(self, skel):
		pass


Formmailer.html = True
