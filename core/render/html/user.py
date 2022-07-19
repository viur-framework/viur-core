import time, json
from string import Template
from . import default as DefaultRender
from viur.core.skeleton import Skeleton


class Render(DefaultRender):  # Render user-data to xml
    loginTemplate = "user_login"
    loginChoicesTemplate = "user_login_choices"
    logoutSuccessTemplate = "user_logout_success"
    loginSuccessTemplate = "user_login_success"
    verifySuccessTemplate = "user_verify_success"
    verifyFailedTemplate = "user_verify_failed"
    passwdRecoverInfoTemplate = "user_passwdrecover_info"

    def login_disabled(self, authMethods, tpl=None, **kwargs):
        if "loginTemplate" in dir(self.parent):
            tpl = tpl or self.parent.loginTemplate
        else:
            tpl = tpl or self.loginTemplate

        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(authMethods=authMethods, **kwargs)

    def login(self, skel, tpl=None, **kwargs):
        if "loginTemplate" in dir(self.parent):
            tpl = tpl or self.parent.loginTemplate
        else:
            tpl = tpl or self.loginTemplate
        return self.add(skel, tpl=tpl, loginFailed=kwargs.get("loginFailed", False),
                        accountStatus=kwargs.get("accountStatus"))

    def loginChoices(self, authMethods, tpl=None, **kwargs):
        if "loginChoicesTemplate" in dir(self.parent):
            tpl = tpl or self.parent.loginChoicesTemplate
        else:
            tpl = tpl or self.loginChoicesTemplate
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(authMethods=authMethods, **kwargs)

    def loginSucceeded(self, tpl=None, **kwargs):
        if "loginSuccessTemplate" in dir(self.parent):
            tpl = tpl or self.parent.loginSuccessTemplate
        else:
            tpl = tpl or self.loginSuccessTemplate
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(**kwargs)

    def logoutSuccess(self, tpl=None, **kwargs):
        if "logoutSuccessTemplate" in dir(self.parent):
            tpl = tpl or self.parent.logoutSuccessTemplate
        else:
            tpl = tpl or self.logoutSuccessTemplate
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(**kwargs)

    def verifySuccess(self, skel, tpl=None, **kwargs):
        if "verifySuccessTemplate" in dir(self.parent):
            tpl = tpl or self.parent.verifySuccessTemplate
        else:
            tpl = tpl or self.verifySuccessTemplate
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(**kwargs)

    def verifyFailed(self, tpl=None, **kwargs):
        if "verifyFailedTemplate" in dir(self.parent):
            tpl = tpl or self.parent.verifyFailedTemplate
        else:
            tpl = tpl or self.verifyFailedTemplate
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(**kwargs)

    def passwdRecoverInfo(self, msg, skel=None, tpl=None, **kwargs):
        if "passwdRecoverInfoTemplate" in dir(self.parent):
            tpl = tpl or self.parent.passwdRecoverInfoTemplate
        else:
            tpl = tpl or self.passwdRecoverInfoTemplate
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        if skel:
            skel.renderPreparation = self.renderBoneValue
        return template.render(skel=skel, msg=msg, **kwargs)

    def passwdRecover(self, *args, **kwargs):
        return self.edit(*args, **kwargs)
