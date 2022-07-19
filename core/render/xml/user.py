import time, json
from string import Template
from viur.core.render.xml.default import DefaultRender, serializeXML


class UserRender(DefaultRender):  # Render user-data to xml
    def login(self, application, skel, failed):
        return self.edit(application, skel, failed=failed, listname="login")

    def loginSucceeded(self):
        return serializeXML(True)

    def renderList(self, skellist):
        return super(render, self).renderList(skellist)

    def renderAddItemSuccess(self, **kwargs):
        return self.renderNoticeRedir("users_note_registration_complete")

    def renderLostpw(self, skel, failed=False):
        return self.renderEdit(skel, failed=failed, listname="lostpassword")

    def renderLostpwSuccess(self, **kwargs):
        return self.renderNoticeRedir("users_note_lostpassword_complete")

    def renderLostpwRequested(self, *args, **kwargs):
        return self.renderNoticeRedir("users_note_lostpassword_requested")
