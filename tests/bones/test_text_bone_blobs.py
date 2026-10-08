"""
Tests for the file-aware side of :class:`viur.core.bones.text.TextBone`:
construction rules, blob collection from embedded files, and the src-set refresh.
"""
from unittest import mock

from abstract import ViUROverlayTestCase

# imported for its side effect: registers the "file" skeleton
import skeletons.overlay_fixtures  # noqa: F401


class TextBoneTestCase(ViUROverlayTestCase):

    def setUp(self):
        super().setUp()
        from viur.core import conf

        self._main_app = conf.main_app
        conf.main_app = mock.Mock()
        self.addCleanup(setattr, conf, "main_app", self._main_app)

    def _bone(self, **kwargs):
        from viur.core.bones.text import TextBone

        bone = TextBone(descr="Body", **kwargs)
        bone.name = "body"
        return bone

    def _with_files(self, *dlkeys):
        """Make conf.main_app.json.file resolve any src to the given download keys in turn."""
        from viur.core import conf

        paths = [mock.Mock(dlkey=dlkey, filename=f"{dlkey}.png", is_derived=False) for dlkey in dlkeys]
        conf.main_app.json.file.parse_download_url.side_effect = paths + [None] * 20
        conf.main_app.json.file.create_download_url.return_value = "/download/url"
        conf.main_app.json.file.create_src_set.return_value = "/download/url 100w"


class TestConstruction(TextBoneTestCase):

    def test_the_legacy_maxLength_argument_still_works_but_warns(self):
        import warnings

        from viur.core.bones.text import TextBone

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            bone = TextBone(descr="Body", maxLength=10)

        self.assertEqual(10, bone.max_length)
        self.assertTrue(any(w.category is DeprecationWarning for w in caught))

    def test_unsanitized_content_requires_no_html_configuration(self):
        from viur.core.bones.text import TextBone

        with self.assertRaises(ValueError):
            TextBone(descr="Body", escape_html=False)

    def test_unsanitized_content_is_allowed_without_a_configuration(self):
        bone = self._bone(escape_html=False, validHtml=None)

        self.assertFalse(bone.escape_html)

    def test_serialization_passes_the_value_through(self):
        self.assertEqual("<p>x</p>", self._bone().singleValueSerialize("<p>x</p>", {}, "body", False))

    def test_unsanitized_input_is_stored_verbatim(self):
        bone = self._bone(escape_html=False, validHtml=None)

        value, errors = bone.singleValueFromClient("<script>alert(1)</script>", {}, "body", {})

        self.assertEqual("<script>alert(1)</script>", value)
        self.assertIsNone(errors)

    def test_sanitized_input_is_cleaned(self):
        bone = self._bone()

        value, errors = bone.singleValueFromClient("<script>alert(1)</script>", {}, "body", {})

        self.assertNotIn("<script", value)
        self.assertIsNone(errors)

    def test_a_missing_value_is_reported(self):
        value, errors = self._bone().singleValueFromClient(None, {}, "body", {})

        self.assertEqual(1, len(errors))

    def test_an_overlong_value_is_reported(self):
        value, errors = self._bone(max_length=5).singleValueFromClient("far too long", {}, "body", {})

        self.assertEqual(1, len(errors))


class TestReferencedBlobs(TextBoneTestCase):

    def test_a_document_without_files_references_nothing(self):
        bone = self._bone()
        self._with_files()

        self.assertEqual(set(), bone.getReferencedBlobs({"body": "<p>text</p>"}, "body"))

    def test_an_embedded_image_is_reported(self):
        bone = self._bone()
        self._with_files("dk1")

        self.assertEqual({"dk1"}, bone.getReferencedBlobs({"body": '<img src="/file/dk1">'}, "body"))

    def test_an_empty_bone_references_nothing(self):
        bone = self._bone()
        self._with_files()

        self.assertEqual(set(), bone.getReferencedBlobs({"body": None}, "body"))

    def test_unsanitized_content_is_not_scanned(self):
        """Without escape_html the value is not treated as HTML at all."""
        bone = self._bone(escape_html=False, validHtml=None)
        self._with_files("dk1")

        self.assertEqual(set(), bone.getReferencedBlobs({"body": '<img src="/file/dk1">'}, "body"))

    def test_a_srcset_bone_schedules_the_derives(self):
        from viur.core import db

        bone = self._bone(srcSet={"width": [100, 200]})
        self._with_files("dk1")

        entity = {"dlkey": "dk1", "creationdate": None}
        db.put("file", entity)

        skel = mock.MagicMock()
        skel.__getitem__.side_effect = {"body": '<img src="/file/dk1">', "key": db.objectid.new_id()}.__getitem__
        skel.kindName = "test_holder"

        with mock.patch("viur.core.bones.file.ensureDerived") as ensure:
            blobs = bone.getReferencedBlobs(skel, "body")

        self.assertEqual({"dk1"}, blobs)
        ensure.assert_called_once()

    def test_a_srcset_bone_without_a_matching_file_schedules_nothing(self):
        from viur.core import db

        bone = self._bone(srcSet={"width": [100]})
        self._with_files("dk-unknown")

        skel = mock.MagicMock()
        skel.__getitem__.side_effect = {"body": '<img src="/file/x">', "key": db.objectid.new_id()}.__getitem__
        skel.kindName = "test_holder"

        with mock.patch("viur.core.bones.file.ensureDerived") as ensure:
            bone.getReferencedBlobs(skel, "body")

        ensure.assert_not_called()


class TestRefresh(TextBoneTestCase):

    def test_unsanitized_content_is_unescaped_on_refresh(self):
        bone = self._bone(escape_html=False, validHtml=None)
        skel = {"body": "&lt;b&gt;"}

        bone.refresh(skel, "body")

        self.assertEqual("<b>", skel["body"])

    def test_an_empty_unsanitized_bone_becomes_the_empty_value(self):
        bone = self._bone(escape_html=False, validHtml=None)
        skel = {"body": None}

        bone.refresh(skel, "body")

        self.assertEqual("", skel["body"])

    def test_a_multiple_unsanitized_bone_refreshes_every_value(self):
        bone = self._bone(escape_html=False, validHtml=None, multiple=True)
        skel = {"body": ["&lt;a&gt;", "&lt;b&gt;"]}

        bone.refresh(skel, "body")

        self.assertEqual(["<a>", "<b>"], skel["body"])

    def test_a_language_aware_unsanitized_bone_refreshes_every_language(self):
        bone = self._bone(escape_html=False, validHtml=None, languages=["de", "en"])
        skel = {"body": {"de": "&lt;a&gt;", "en": "&lt;b&gt;"}}

        bone.refresh(skel, "body")

        self.assertEqual({"de": "<a>", "en": "<b>"}, skel["body"])

    def test_a_srcset_bone_reparses_its_content(self):
        bone = self._bone(srcSet={"width": [100]})
        self._with_files()
        skel = {"body": "<p>text</p>"}

        bone.refresh(skel, "body")

        self.assertIn("text", skel["body"])

    def test_a_srcset_bone_reparses_every_language(self):
        bone = self._bone(srcSet={"width": [100]}, languages=["de"])
        self._with_files()
        skel = {"body": {"de": "<p>text</p>"}}

        bone.refresh(skel, "body")

        self.assertIn("text", skel["body"]["de"])

    def test_a_bone_without_a_srcset_is_left_alone(self):
        bone = self._bone()
        skel = {"body": "<p>text</p>"}

        bone.refresh(skel, "body")

        self.assertEqual("<p>text</p>", skel["body"])


class TestRemainingTextBranches(TextBoneTestCase):

    def test_an_empty_entry_of_a_multiple_bone_contributes_no_blob(self):
        bone = self._bone(multiple=True)
        self._with_files()

        self.assertEqual(set(), bone.getReferencedBlobs({"body": [None, ""]}, "body"))

    def test_a_none_entry_survives_the_unsanitized_refresh(self):
        bone = self._bone(escape_html=False, validHtml=None, multiple=True)
        skel = {"body": [None, "&lt;b&gt;"]}

        bone.refresh(skel, "body")

        self.assertEqual([None, "<b>"], skel["body"])

    def test_a_srcset_bone_with_an_unexpected_value_type_is_left_alone(self):
        bone = self._bone(srcSet={"width": [100]})
        skel = {"body": ["<p>a</p>"]}

        bone.refresh(skel, "body")

        self.assertEqual(["<p>a</p>"], skel["body"])
