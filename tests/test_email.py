"""Tests for the guards in :mod:`viur.core.email`.

Anything from :mod:`viur.core` is imported inside the test methods, see
:mod:`tests.test_securityheaders` for the reason.
"""
from unittest import mock

from abstract import ViURTestCase


class TestSendEmailOnDevServer(ViURTestCase):
    """The App Engine Mail API is never reachable from a local development server.

    ``conf.email.transport_class`` holds an *instance*, so the guard has to use
    ``isinstance``. Comparing against the class was always False and let the call through
    to fail inside the API instead.
    """

    def _send(self, transport_class, send_from_local_development_server: bool) -> tuple:
        """Call ``send_email`` on a simulated dev server.

        :return: Tuple of the return value and the mock that replaced ``db.put``.
        """
        from viur.core import email
        from viur.core.config import conf

        # conf.emailRenderer is only wired up by viur.core.setup()
        conf.emailRenderer = lambda *args, **kwargs: ("subject", "body")
        self.addCleanup(delattr, conf, "emailRenderer")

        with mock.patch.object(conf.email, "transport_class", transport_class), \
                mock.patch.object(conf.email, "send_from_local_development_server",
                                  send_from_local_development_server), \
                mock.patch.object(conf.instance, "is_dev_server", True), \
                mock.patch.object(email.db, "put") as put, \
                mock.patch.object(email, "send_email_deferred"):
            result = email.send_email(dests="user@example.com", stringTemplate="hello")

        return result, put

    def test_appengine_transport_is_never_used_locally(self):
        from viur.core.email import EmailTransportAppengine
        result, put = self._send(EmailTransportAppengine(), send_from_local_development_server=True)
        self.assertFalse(result)
        put.assert_not_called()

    def test_other_transport_may_send_when_enabled(self):
        from viur.core.email import EmailTransportSmtp
        transport = EmailTransportSmtp(host="localhost", user="u", password="p")
        result, put = self._send(transport, send_from_local_development_server=True)
        self.assertTrue(result)
        put.assert_called_once()

    def test_other_transport_is_blocked_when_disabled(self):
        from viur.core.email import EmailTransportSmtp
        transport = EmailTransportSmtp(host="localhost", user="u", password="p")
        result, put = self._send(transport, send_from_local_development_server=False)
        self.assertFalse(result)
        put.assert_not_called()


class TestCheckBrevoQuota(ViURTestCase):
    """The quota check must run for :class:`EmailTransportBrevo`, not only for its
    deprecated subclass :class:`EmailTransportSendInBlue`."""

    def _check(self, transport_class) -> mock.Mock:
        """Run ``check_sib_quota`` and return the mock that replaced ``requests.get``."""
        from viur.core import email
        from viur.core.config import conf

        response = mock.Mock()
        response.ok = False
        with mock.patch.object(conf.email, "transport_class", transport_class), \
                mock.patch.object(email.requests, "get", return_value=response) as get:
            email.EmailTransportBrevo.check_sib_quota()

        return get

    def test_brevo_transport_is_checked(self):
        from viur.core.email import EmailTransportBrevo
        self._check(EmailTransportBrevo(api_key="key")).assert_called_once()

    def test_deprecated_subclass_is_still_checked(self):
        from viur.core.email import EmailTransportSendInBlue
        self._check(EmailTransportSendInBlue(api_key="key")).assert_called_once()

    def test_other_transport_is_skipped(self):
        from viur.core.email import EmailTransportSmtp
        transport = EmailTransportSmtp(host="localhost", user="u", password="p")
        self._check(transport).assert_not_called()
