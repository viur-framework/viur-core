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


class TestSendEmailCloudStorageOffload(ViURTestCase):
    """Inline attachment content and large bodies must not stay in the queue entity (1 MiB datastore limit)."""

    BODY_PATH = "viur-emails/4711/body.html"

    def setUp(self) -> None:
        super().setUp()
        from viur.core import db
        from viur.core.config import conf
        self.conf = conf
        self.bucket = mock.MagicMock(name="bucket")
        self.main_app = mock.MagicMock(name="main_app")
        self.main_app.file.get_bucket.return_value = self.bucket
        self.key = db.Key("viur-emails", 4711)

    def _send(self, body: str = "hello", transport=None, **kwargs):
        """Queue one email with mocked datastore and storage; returns the entity passed to db.put (or None)."""
        from viur.core import email
        from viur.core.email import EmailTransportSmtp
        conf = self.conf
        conf.emailRenderer = lambda *args, **kw: ("subject", body)
        self.addCleanup(delattr, conf, "emailRenderer")
        transport = transport or EmailTransportSmtp(host="localhost", user="u", password="p")
        with mock.patch.object(conf.email, "transport_class", transport), \
                mock.patch.object(conf.instance, "is_dev_server", False), \
                mock.patch.object(conf, "main_app", self.main_app), \
                mock.patch.object(email.db, "allocate_ids", return_value=[self.key]) as self.allocate_ids, \
                mock.patch.object(email.db, "put") as self.put, \
                mock.patch.object(email, "send_email_deferred"):
            email.send_email(dests="user@example.com", stringTemplate="hello", **kwargs)
        if self.put.called:
            (entity,), _ = self.put.call_args
            return entity
        return None

    def test_inline_attachment_content_is_stored_in_cloud_storage(self) -> None:
        entity = self._send(attachments=[{"filename": "a.pdf", "content": b"%PDF-1.4", "mimetype": "application/pdf"}])
        path = "viur-emails/4711/attachment-0/a.pdf"
        self.bucket.blob.assert_called_once_with(path)
        self.bucket.blob.return_value.upload_from_string.assert_called_once_with(
            b"%PDF-1.4", content_type="application/pdf")
        (attachment,) = entity["attachments"]
        self.assertEqual(attachment["gcsfile"], path)
        self.assertNotIn("content", attachment)
        self.assertEqual(attachment["filename"], "a.pdf")

    def test_small_body_stays_in_the_entity(self) -> None:
        entity = self._send(body="hello")
        self.assertEqual(entity["body"], "hello")
        self.assertNotIn("body_gcsfile", entity)
        self.bucket.blob.assert_not_called()
        self.allocate_ids.assert_not_called()

    def test_large_body_is_stored_in_cloud_storage(self) -> None:
        body = "<p>" + "x" * 100 + "</p>"
        with mock.patch.object(self.conf.email, "body_offload_threshold", 10):
            entity = self._send(body=body)
        self.bucket.blob.assert_called_once_with(self.BODY_PATH)
        self.bucket.blob.return_value.upload_from_string.assert_called_once_with(
            body.encode("utf-8"), content_type="text/html; charset=utf-8")
        self.assertIsNone(entity["body"])
        self.assertEqual(entity["body_gcsfile"], self.BODY_PATH)
        self.assertEqual(entity.key, self.key)

    def test_entity_above_the_datastore_limit_is_rejected_before_put(self) -> None:
        with self.assertRaises(ValueError):
            self._send(context={"blob": b"x" * (1024 * 1024 + 1)})
        self.assertFalse(self.put.called)

    def test_transport_message_size_limit_is_checked_before_queueing(self) -> None:
        from viur.core.email import EmailTransportSmtp
        transport = EmailTransportSmtp(host="localhost", user="u", password="p")
        transport.max_message_size = 10
        with self.assertRaises(ValueError):
            self._send(body="x" * 100, transport=transport)
        self.assertFalse(self.put.called)
        self.bucket.blob.assert_not_called()

    def test_transport_message_size_counts_gcsfile_attachments_by_metadata(self) -> None:
        from viur.core.email import EmailTransportSmtp
        transport = EmailTransportSmtp(host="localhost", user="u", password="p")
        transport.max_message_size = 50
        self.bucket.get_blob.return_value.size = 100
        with self.assertRaises(ValueError):
            self._send(body="hi", transport=transport, attachments=[{"filename": "a.pdf", "gcsfile": "x/y/a.pdf"}])
        self.bucket.get_blob.return_value.download_as_bytes.assert_not_called()
        self.assertFalse(self.put.called)

    def test_send_email_deferred_loads_the_body_from_cloud_storage(self) -> None:
        import io
        from viur.core import db, email
        conf = self.conf
        entity = db.Entity(self.key)
        entity |= {"isSend": False, "errorCount": 0, "sender": "s@example.com", "dests": ["d@example.com"],
                   "cc": None, "bcc": None, "subject": "subject", "body": None, "body_gcsfile": self.BODY_PATH,
                   "headers": None, "attachments": None}
        self.main_app.vi.file.read.return_value = (io.BytesIO(b"<p>hi</p>"), "text/html; charset=utf-8")
        transport = mock.MagicMock(spec=email.EmailTransport)
        with mock.patch.object(conf.email, "transport_class", transport), \
                mock.patch.object(conf, "main_app", self.main_app), \
                mock.patch.object(email.db, "get", return_value=entity), \
                mock.patch.object(email.db, "put"):
            email.send_email_deferred(self.key, _call_deferred=False)
        self.main_app.vi.file.read.assert_called_once_with(path=self.BODY_PATH)
        self.assertEqual(transport.deliver_email.call_args.kwargs["body"], "<p>hi</p>")

    def test_delete_cloud_storage_objects_removes_everything_below_the_prefix(self) -> None:
        from viur.core import email
        blobs = [mock.MagicMock(name="body"), mock.MagicMock(name="attachment")]
        self.bucket.list_blobs.return_value = blobs
        with mock.patch.object(self.conf, "main_app", self.main_app):
            email.delete_cloud_storage_objects(self.key)
        self.bucket.list_blobs.assert_called_once_with(prefix="viur-emails/4711/")
        for blob in blobs:
            blob.delete.assert_called_once_with()


class TestEmailModuleDeletion(ViURTestCase):
    """Deleting a queued email, by hand or by the retention task, must delete its Cloud Storage objects too."""

    def setUp(self) -> None:
        super().setUp()
        from viur.core.config import conf
        self.conf = conf
        self.bucket = mock.MagicMock(name="bucket")
        self.main_app = mock.MagicMock(name="main_app")
        self.main_app.file.get_bucket.return_value = self.bucket

    def test_module_on_deleted_removes_the_objects(self) -> None:
        from viur.core import db
        from viur.core.modules.email import Email
        skel = {"key": db.Key("viur-emails", 4711)}
        with mock.patch.object(self.conf, "main_app", self.main_app), \
                mock.patch("viur.core.prototypes.list.List.onDeleted") as parent:
            Email.onDeleted(Email.__new__(Email), skel)
        parent.assert_called_once()
        self.bucket.list_blobs.assert_called_once_with(prefix="viur-emails/4711/")

    def test_retention_iter_removes_objects_and_entity(self) -> None:
        from viur.core import db, email
        entity = db.Entity(db.Key("viur-emails", 4711))
        with mock.patch.object(self.conf, "main_app", self.main_app), \
                mock.patch.object(email.db, "delete") as delete:
            email.DeleteEmailsIter.handleEntry(entity, None)
        self.bucket.list_blobs.assert_called_once_with(prefix="viur-emails/4711/")
        delete.assert_called_once_with(entity.key)
