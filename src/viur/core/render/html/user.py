import typing as t

from . import default as DefaultRender
from viur.core.modules.user import UserSecondFactorAuthentication

class Render(DefaultRender):  # Render user-data to xml
    loginTemplate = "user_login"
    loginChoicesTemplate = "user_login_choices"
    logoutSuccessTemplate = "user_logout_success"
    loginSuccessTemplate = "user_login_success"
    verifySuccessTemplate = "user_verify_success"
    verifyFailedTemplate = "user_verify_failed"
    passwdRecoverInfoTemplate = "user_passwdrecover_info"
    second_factor_add_template = "user_secondfactor_add"
    second_factor_add_success_template = "user_secondfactor_add_success"
    second_factor_choice_template = "user_second_factor_choice"

    def _choose_template(self, tpl: None | str, fallback_attribute: str) -> str:
        if tpl:
            return tpl
        if hasattr(self.parent, fallback_attribute):
            return getattr(self.parent, fallback_attribute)
        return getattr(self, fallback_attribute)

    def login_disabled(self, authMethods, tpl: str | None = None, **kwargs):
        tpl = self._choose_template(tpl, "loginTemplate")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(authMethods=authMethods, **kwargs)

    def login(self, skel, tpl: str | None = None, **kwargs):
        tpl = self._choose_template(tpl, "loginTemplate")
        return self.add(skel, tpl=tpl, loginFailed=kwargs.get("loginFailed", False),
                        accountStatus=kwargs.get("accountStatus"))

    def loginChoices(self, authMethods, tpl: str | None = None, **kwargs):
        tpl = self._choose_template(tpl, "loginChoicesTemplate")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(authMethods=authMethods, **kwargs)

    def loginSucceeded(self, tpl: str | None = None, **kwargs):
        tpl = self._choose_template(tpl, "loginSuccessTemplate")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(**kwargs)

    def logoutSuccess(self, tpl: str | None = None, **kwargs):
        tpl = self._choose_template(tpl, "logoutSuccessTemplate")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(**kwargs)

    def verifySuccess(self, skel, tpl: str | None = None, **kwargs):
        tpl = self._choose_template(tpl, "verifySuccessTemplate")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(**kwargs)

    def verifyFailed(self, tpl: str | None = None, **kwargs):
        tpl = self._choose_template(tpl, "verifyFailedTemplate")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(**kwargs)

    def passwdRecoverInfo(self, msg, skel=None, tpl: str | None = None, **kwargs):
        tpl = self._choose_template(tpl, "passwdRecoverInfoTemplate")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        if skel:
            skel.renderPreparation = self.renderBoneValue
        return template.render(skel=skel, msg=msg, **kwargs)

    def passwdRecover(self, *args, **kwargs):
        return self.edit(*args, **kwargs)

    def second_factor_add(self, action_name: str, name: str, add_url: str,
                          tpl: str | None, otp_uri=None):
        tpl = self._choose_template(tpl, "second_factor_add_template")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(action_name=action_name, name=name, add_url=add_url, otp_uri=otp_uri)

    def second_factor_add_success(self, action_name: str, name: str, tpl: str | None = None):
        tpl = self._choose_template(tpl, "second_factor_add_success_template")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(action_name=action_name, name=name)

    def second_factor_choice(self,
                             second_factors: t.Iterable[UserSecondFactorAuthentication],
                             tpl: str | None = None):
        tpl = self._choose_template(tpl, "second_factor_choice_template")
        template = self.getEnv().get_template(self.getTemplateFileName(tpl))
        return template.render(second_factors=second_factors)
