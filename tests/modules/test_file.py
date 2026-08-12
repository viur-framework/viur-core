import datetime
from unittest import mock

from abstract import ViURTestCase


class TestFileDownloadUrl(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core import conf
        conf.file_hmac_key = b"test-hmac-key-for-unit-tests"

    def _roundtrip(self, filename, *, derived=False, expires=None):
        """create_download_url → parse_download_url round-trip, returns parsed FilePath."""
        # Lazy import: viur.core.modules.file initializes a GCS client at module level.
        # Importing inside a test method ensures the AppEngine testbed is already active,
        # so google.auth.default() is mocked and storage.Client() won't fail.
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        url = File.create_download_url("testdlkey", filename, derived=derived, expires=expires)
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

    def test_expiring_url(self):
        """A signature carrying a lifetime must parse while that lifetime lasts."""
        result = self._roundtrip("document.pdf", expires=datetime.timedelta(hours=1))
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "document.pdf")

    def test_expired_url(self):
        """A signature whose lifetime has passed must not parse."""
        self.assertIsNone(self._roundtrip("document.pdf", expires=datetime.timedelta(hours=-1)))

    def _create_url(self, filename, *, derived=False, expires=None, download_filename=None):
        """Create a download url without parsing it back."""
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        return File.create_download_url(
            "testdlkey", filename, derived=derived, expires=expires,
            download_filename=download_filename)

    def test_absolute_url(self):
        """Admin frontends store the url including scheme and host; it must still parse."""
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        url = self._create_url("document.pdf")
        result = File.parse_download_url(f"https://example.com{url}")
        self.assertIsNotNone(result)
        self.assertEqual(result.dlkey, "testdlkey")
        self.assertEqual(result.filename, "document.pdf")

    def test_trailing_slash_before_query(self):
        """A slash between payload and query string must not break the signature check."""
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        data, _, query = self._create_url("document.pdf").removeprefix(
            File.DOWNLOAD_URL_PREFIX).partition("?")
        result = File.parse_download_url(f"{File.DOWNLOAD_URL_PREFIX}{data}/?{query}")
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "document.pdf")

    def test_url_with_download_filename_path_segment(self):
        """`download` accepts the file name as a path segment, so parsing must ignore it."""
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        data, _, query = self._create_url(
            "document.pdf", download_filename="nice-name.pdf").removeprefix(
            File.DOWNLOAD_URL_PREFIX).partition("?")
        result = File.parse_download_url(
            f"{File.DOWNLOAD_URL_PREFIX}{data}/nice-name.pdf?{query}")
        self.assertIsNotNone(result)
        self.assertEqual(result.dlkey, "testdlkey")
        self.assertEqual(result.filename, "document.pdf")

    def test_query_with_additional_parameters(self):
        """Other query parameters next to `sig` must not confuse the parser."""
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        url = self._create_url("document.pdf")
        result = File.parse_download_url(f"{url}&download=1")
        self.assertIsNotNone(result)
        self.assertEqual(result.filename, "document.pdf")

    def test_url_without_query_is_rejected(self):
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        url = self._create_url("document.pdf").split("?", 1)[0]
        self.assertIsNone(File.parse_download_url(url))
