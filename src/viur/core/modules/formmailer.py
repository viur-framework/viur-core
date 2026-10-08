from viur.core.skeleton import RelSkel
from viur.core import errors, utils, securitykey, email
from viur.core.decorators import *
from viur.core.bones import BaseBone
from viur.core.module import Module


class MailSkel(RelSkel):
    changedate = None  # Changedates won't apply here


class Formmailer(Module):
    """
    Formmailer is the standard module to implement a form mailer for contact request or similar forms.
    """

    mailTemplate = None

    @exposed
    def index(self, *args, **kwargs):
        if not self.canIndex(None):
            raise errors.Unauthorized()

        return self.add(*args, **kwargs)

    @exposed
    @skey(allow_empty=True)
    def add(self, *args, **kwargs):
        skel = self.mailSkel()
        if not self.canAdd(skel):
            raise errors.Forbidden()

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

        # Get additional options for send_email
        opts = self.getOptions(skel)
        if not isinstance(opts, dict):
            opts = {}

        self.onAdd(skel)
        email.send_email(dests=rcpts, tpl=self.mailTemplate, skel=skel, **opts)
        self.thenAdd(skel)

        return self.render.addSuccess(skel)

    def canIndex(self, skel: None) -> bool:
        """
        Access control function for :func:`index`; allowed, as index only forwards to :func:`add`.
        """
        return True

    def canAdd(self, skel: RelSkel) -> bool:
        """
        Access control function for sending the form; refused until a formmailer allows it.

        :param skel: The form, as returned by :func:`mailSkel`.
        """
        return False

    def mailSkel(self):
        raise NotImplementedError("You must implement the \"mailSkel\" function!")

    def getRcpts(self, skel):
        raise NotImplementedError("You must implement the \"getRcpts\" function!")

    def getOptions(self, skel):
        return None

    def onAdd(self, skel: RelSkel):
        """Hook function that is called before the mail is sent."""
        pass

    def thenAdd(self, skel: RelSkel):
        """Hook function that is called after the mail was sent."""
        pass


Formmailer.html = True
