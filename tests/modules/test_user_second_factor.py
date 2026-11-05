"""Tests for the template context of the second factor login steps."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from abstract import ViURTestCase  # noqa: E402


class TestSecondFactorTemplateParams(ViURTestCase):
    """The login template must get ``name``, ``action_name`` and ``action_url`` the same way on every step.

    ``start`` passes them as ``params``; the "wrong token" responses passed them as plain keyword arguments,
    so a template written for one of the two steps rendered the other one empty.
    """

    def _factor(self, cls):
        """Build a second factor provider bound to a mocked user module.

        :param cls: The second factor class to instantiate.
        :return: Tuple of the provider and the mocked ``render.edit``.
        """
        user_module = mock.MagicMock()
        user_module.kindName = "user"
        provider = object.__new__(cls)
        provider._user_module = user_module
        provider.modulePath = "/user/f2_test"
        provider.action_url = f"{provider.modulePath}/{cls.ACTION_NAME}"
        return provider, user_module.render.edit

    def _session(self, conf: dict) -> dict:
        """Put a session holding the given OTP configuration into the request context."""
        from viur.core import current
        session = mock.MagicMock()
        data = {"_otp_user": conf, "possible_user_key": 1}
        session.get.side_effect = data.get
        session.__getitem__.side_effect = data.__getitem__
        token = current.session.set(session)
        self.addCleanup(current.session.reset, token)
        return data

    def _assert_params(self, edit: mock.Mock, action_name: str):
        edit.assert_called_once()
        kwargs = edit.call_args.kwargs
        self.assertNotIn("action_name", kwargs)
        self.assertEqual(action_name, kwargs["params"]["action_name"])
        self.assertEqual(f"/user/f2_test/{action_name}", kwargs["params"]["action_url"])
        self.assertIn("name", kwargs["params"])

    def test_time_based_otp_wrong_token_uses_params(self):
        from viur.core.modules.user import TimeBasedOTP

        provider, edit = self._factor(TimeBasedOTP)
        self._session({"secret": "00" * 20, "attempts": 0})
        with mock.patch.object(TimeBasedOTP, "verify", return_value=None):
            TimeBasedOTP.otp._func(provider, otptoken="123456")
        self._assert_params(edit, TimeBasedOTP.ACTION_NAME)

    def test_authenticator_otp_wrong_token_uses_params(self):
        from viur.core.modules import user as user_mod

        provider, edit = self._factor(user_mod.AuthenticatorOTP)
        self._session({"attempts": 0})
        with mock.patch.object(user_mod.db, "get", return_value={"otp_app_secret": "JBSWY3DPEHPK3PXP"}), \
                mock.patch.object(user_mod.AuthenticatorOTP, "verify_otp", return_value=False):
            user_mod.AuthenticatorOTP.authenticator_otp._func(provider, otptoken="123456")
        self._assert_params(edit, user_mod.AuthenticatorOTP.ACTION_NAME)
