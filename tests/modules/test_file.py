from unittest import mock

from abstract import ViURTestCase


class TestFileDownloadUrl(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core import conf
        conf.file_hmac_key = b"test-hmac-key-for-unit-tests"

    def _roundtrip(self, filename, *, derived=False):
        """create_download_url → parse_download_url round-trip, returns parsed FilePath."""
        # Lazy import: viur.core.modules.file initializes a GCS client at module level.
        # Importing inside a test method ensures the AppEngine testbed is already active,
        # so google.auth.default() is mocked and storage.Client() won't fail.
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        url = File.create_download_url("testdlkey", filename, derived=derived, expires=None)
        return File.parse_download_url(url)

    def test_plain_filename(self):
        result = self._roundtrip("document.pdf")
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "document.pdf")
        self.assertEqual(result.dlkey, "testdlkey")
        self.assertFalse(result.is_derived)

    def test_unescape_short_form_entities(self):
        """Short-form entities &#40; &#41; &#61; must be unescaped in the filepath."""
        result = self._roundtrip("file&#40;1&#41;&#61;x.pdf")
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "file(1)=x.pdf")

    def test_unescape_long_form_entities(self):
        """Long-form entities &#040; &#041; &#061; must be unescaped in the filepath."""
        result = self._roundtrip("file&#040;1&#041;&#061;x.pdf")
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "file(1)=x.pdf")

    def test_unescape_other_html_entities(self):
        """html.unescape() also handles &lt; &gt; — consistent with the rename code in the same module."""
        result = self._roundtrip("&lt;test&gt;.pdf")
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "<test>.pdf")

    def test_derived_flag(self):
        result = self._roundtrip("thumb.webp", derived=True)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_derived)
        self.assertEqual(result.filename, "thumb.webp")


class TestFileHmacRotation(ViURTestCase):
    """conf.file_hmac_key_fallbacks lets hmac_verify accept signatures made with a retired key,
    so file_hmac_key can be rotated without invalidating already-signed download URLs."""

    def _file(self):
        # See TestFileDownloadUrl._roundtrip for why the import is mocked and lazy.
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        return File

    def tearDown(self):
        from viur.core import conf
        conf.file_hmac_key = None
        conf.file_hmac_key_fallbacks = []
        super().tearDown()

    def test_rotated_key_still_verifies_old_signature(self):
        from viur.core import conf
        File = self._file()
        conf.file_hmac_key = b"old-key"
        old_sig = File.hmac_sign("payload")
        # Rotate: new active key, old key retired into fallbacks.
        conf.file_hmac_key = b"new-key"
        conf.file_hmac_key_fallbacks = [b"old-key"]
        self.assertTrue(File.hmac_verify("payload", old_sig))  # old sig still accepted
        self.assertTrue(File.hmac_verify("payload", File.hmac_sign("payload")))  # new sig accepted

    def test_old_signature_rejected_without_fallback(self):
        from viur.core import conf
        File = self._file()
        conf.file_hmac_key = b"old-key"
        old_sig = File.hmac_sign("payload")
        conf.file_hmac_key = b"new-key"
        conf.file_hmac_key_fallbacks = []
        self.assertFalse(File.hmac_verify("payload", old_sig))  # no fallback -> rejected

    def test_str_fallback_key_is_accepted(self):
        """Operators may configure a retired key as str; it is coerced like the active key."""
        from viur.core import conf
        File = self._file()
        conf.file_hmac_key = b"old-key"
        old_sig = File.hmac_sign("payload")
        conf.file_hmac_key = b"new-key"
        conf.file_hmac_key_fallbacks = ["old-key"]  # str, not bytes
        self.assertTrue(File.hmac_verify("payload", old_sig))

    def test_garbage_signature_rejected(self):
        from viur.core import conf
        File = self._file()
        conf.file_hmac_key = b"new-key"
        conf.file_hmac_key_fallbacks = [b"old-key"]
        self.assertFalse(File.hmac_verify("payload", "deadbeef"))
