import base64
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


class FakeFileSkel(dict):
    """Minimal stand-in for the skeleton returned by ``File.addSkel("leaf")``."""

    def write(self):
        self["key"] = "written-key"
        return self


class TestFileWriteWeakFlag(ViURTestCase):
    """``File.write`` marks a file weak exactly when it ends up without a repository."""

    def _write(self, **kwargs):
        """Run File.write against faked storage and skeletons, return the leaf skeleton."""
        from unittest import mock as _mock
        with _mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File

        blob = mock.Mock(size=4, crc32c=base64.b64encode(b"1234").decode(), md5_hash=base64.b64encode(b"5678").decode())
        bucket = mock.Mock()
        bucket.blob.return_value = blob

        leaf_skel = FakeFileSkel()

        module = mock.Mock()
        module.is_valid_filename = File.is_valid_filename
        module.get_bucket.return_value = bucket
        module.addSkel.side_effect = lambda kind: leaf_skel if kind == "leaf" else mock.Mock()

        File.write(module, "test.txt", b"data", **kwargs)
        return leaf_skel

    def test_file_without_repository_is_weak(self):
        """Documented: "If both are not set, the file is added [...] as a weak file"."""
        skel = self._write()
        self.assertIsNone(skel["parentrepo"])
        self.assertTrue(skel["weak"])

    def test_file_in_a_folder_is_not_weak(self):
        """A file inside a repository must keep its blob lock, so it must not be weak."""
        from unittest import mock as _mock
        with _mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File

        blob = mock.Mock(size=4, crc32c=base64.b64encode(b"1234").decode(), md5_hash=base64.b64encode(b"5678").decode())
        bucket = mock.Mock()
        bucket.blob.return_value = blob

        leaf_skel = FakeFileSkel()
        node_skel = mock.Mock()
        node_skel.all.return_value.getSkel.return_value = {"key": "folder-key"}

        module = mock.Mock()
        module.is_valid_filename = File.is_valid_filename
        module.get_bucket.return_value = bucket
        module.addSkel.side_effect = lambda kind: leaf_skel if kind == "leaf" else node_skel
        module.ensureOwnModuleRootNode.return_value = mock.Mock(key="repo-key")

        File.write(module, "test.txt", b"data", folder="documents")

        self.assertEqual("repo-key", leaf_skel["parentrepo"])
        self.assertFalse(leaf_skel["weak"])


class TestCreateSrcSetLanguageWrapper(ViURTestCase):
    """create_src_set has to unwrap a LanguageWrapper, i.e. a FileBone with languages set."""

    def _file(self):
        return {
            "dlkey": "testdlkey",
            "derived": {
                "files": {
                    "thumb.webp": {"customData": {"width": 100, "height": 50}},
                },
            },
        }

    def _wrapper(self, **values):
        from viur.core import i18n
        wrapper = i18n.LanguageWrapper(["de", "en"])
        wrapper.update(values)
        return wrapper

    def setUp(self):
        super().setUp()
        from viur.core import conf
        conf.file_hmac_key = b"test-hmac-key-for-unit-tests"

    def _create_src_set(self, file, **kwargs):
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules.file import File
        return File.create_src_set(file, width=[100], **kwargs)

    def test_explicit_language_is_used(self):
        wrapper = self._wrapper(de=self._file())
        result = self._create_src_set(wrapper, language="de")
        self.assertIn("100w", result)

    def test_missing_language_yields_empty_string(self):
        wrapper = self._wrapper(de=self._file())
        self.assertEqual("", self._create_src_set(wrapper, language="en"))

    def test_current_language_is_used_when_none_given(self):
        from viur.core import current
        wrapper = self._wrapper(de=self._file())
        current.language.set("de")
        try:
            result = self._create_src_set(wrapper)
        finally:
            current.language.set(None)
        self.assertIn("100w", result)

    def test_without_any_language_yields_empty_string(self):
        wrapper = self._wrapper(de=self._file())
        self.assertEqual("", self._create_src_set(wrapper))


class FakeBlobLockQuery:
    """Stands in for db.Query inside doCheckForUnreferencedBlobs."""

    def __init__(self, kind, state):
        self.kind = kind
        self.state = state
        self.filters = []

    def filter(self, *args):
        self.filters.append(args)
        return self

    def setCursor(self, cursor):
        return self

    def run(self, limit):
        return self.state["locks"]

    def getEntry(self):
        prop, value = self.filters[0]
        if prop == "active_blob_references =":
            return None  # nothing references these blobs any more
        if prop == "dlkey":
            return object() if value in self.state["already_marked"] else None
        raise AssertionError(f"unexpected filter {prop!r}")

    def getCursor(self):
        return None


class TestCheckForUnreferencedBlobs(ViURTestCase):
    """A blob that is already marked must not stop the cleanup of the remaining blobs."""

    def _run(self, blob_keys, already_marked):
        with mock.patch("google.cloud.storage.Client"):
            from viur.core.modules import file as file_module

        state = {"locks": [mock.Mock(key="lock-1")], "already_marked": already_marked}
        written = []

        with mock.patch.object(file_module.db, "Query", lambda kind: FakeBlobLockQuery(kind, state)), \
                mock.patch.object(file_module.db, "run_in_transaction", lambda fn, key: blob_keys), \
                mock.patch.object(file_module.db, "Key", lambda *a, **kw: mock.Mock()), \
                mock.patch.object(file_module.db, "Entity", lambda key: {}), \
                mock.patch.object(file_module.db, "put", lambda obj: written.append(obj["dlkey"])):
            file_module.doCheckForUnreferencedBlobs.__wrapped__()

        return written

    def test_marks_all_unreferenced_blobs(self):
        self.assertEqual(["blob-a", "blob-b"], self._run(["blob-a", "blob-b"], already_marked=()))

    def test_already_marked_blob_does_not_stop_the_run(self):
        """The first blob is already scheduled; the second one still has to be picked up."""
        self.assertEqual(["blob-b"], self._run(["blob-a", "blob-b"], already_marked=("blob-a",)))

    def test_all_blobs_already_marked(self):
        self.assertEqual([], self._run(["blob-a", "blob-b"], already_marked=("blob-a", "blob-b")))


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

    def test_explicit_key_matches_default_key(self):
        """hmac_sign(key=None) uses conf.file_hmac_key, an explicit key (bytes or str) yields the same digest."""
        from viur.core import conf
        File = self._file()
        conf.file_hmac_key = b"active-key"
        self.assertEqual(File.hmac_sign("payload"), File.hmac_sign("payload", key=b"active-key"))
        self.assertEqual(File.hmac_sign("payload"), File.hmac_sign("payload", key="active-key"))
        self.assertNotEqual(File.hmac_sign("payload"), File.hmac_sign("payload", key=b"other-key"))
