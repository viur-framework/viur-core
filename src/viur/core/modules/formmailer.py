from viur.core.skeleton import RelSkel
from viur.core import errors, utils, securitykey, email
from viur.core.decorators import *
from viur.core.bones import BaseBone
from viur.core.module import Module


class MailSkel(RelSkel):
    changedate = None  # Changedates won't apply here


class Formmailer(Module):
    mailTemplate = None

    @exposed
    @skey(allow_empty=True)
    def index(self, *args, **kwargs):
        if not self.canUse():
            raise errors.Forbidden()  # Unauthorized

        skel = self.mailSkel()

        if len(kwargs) == 0:
            return self.render.add(skel=skel, failed=False)

        if not skel.fromClient(kwargs):
            return self.render.add(skel=skel, failed=True)

        # Allow bones to perform outstanding "magic" operations before sending the mail
        for key, _bone in skel.items():
            if isinstance(_bone, BaseBone):
                _bone.performMagic(skel, key, isAdd=True)

        # Get recipients
        rcpts = self.getRcpts(skel)

        # Get additional options for sendEMail
        opts = self.getOptions(skel)
        if not isinstance(opts, dict):
            opts = {}

        # Send the email!
        email.sendEMail(dests=rcpts, tpl=self.mailTemplate, skel=skel, **opts)
        self.onAdded(skel)

        return self.render.addSuccess(skel)

    @exposed
    def add(self, *args, **kwargs):
        return self.index(*args, **kwargs)

    def canUse(self) -> bool:
        return False

    def mailSkel(self):
        raise NotImplementedError("You must implement the \"mailSkel\" function!")

    def getRcpts(self, skel):
        raise NotImplementedError("You must implement the \"getRcpts\" function!")

    def getOptions(self, skel):
        return None

    def onAdded(self, skel):
        pass


Formmailer.html = True
