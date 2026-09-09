import mock

from abstract import ViURTestCase


class TestTextBone_fromClient(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from viur.core import conf
        conf.main_app = mock.MagicMock()
        conf.main_app.vi = None
        cls.bone_name = "myTextBone"

    def test_fromClient_single(self):
        from viur.core.bones import TextBone
        from viur.core.bones.base import ReadFromClientError
        bone = TextBone()
        skel = {}
        data = {self.bone_name: "foo"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertIn(self.bone_name, skel)
        self.assertEqual(data[self.bone_name], skel[self.bone_name])
        # invalid data
        data = {self.bone_name: None}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)

    def test_fromClient_multi(self):
        from viur.core.bones import TextBone
        bone = TextBone(multiple=True)
        skel = {}
        data = {self.bone_name: ["foo", "bar"]}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertIn(self.bone_name, skel)
        self.assertListEqual(data[self.bone_name], skel[self.bone_name])

    def test_fromClient_lang(self):
        from viur.core.bones import TextBone
        bone = TextBone(languages=["en", "de"])
        skel = {}
        lang = "de"
        data = {f"{self.bone_name}.{lang}": "foo"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertIn(self.bone_name, skel)
        self.assertIn(lang, skel[self.bone_name])
        self.assertIn("en", skel[self.bone_name])
        self.assertIsNone(skel[self.bone_name]["en"])
        self.assertNotIn("fr", skel[self.bone_name])
        self.assertEqual("foo", skel[self.bone_name][lang])

    def test_fromClient_multi_lang(self):
        from viur.core.bones import TextBone
        bone = TextBone(multiple=True, languages=["en", "de"])
        skel = {}
        lang = "de"
        data = {f"{self.bone_name}.{lang}": ["foo", "bar"]}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertIn(self.bone_name, skel)
        self.assertIn(lang, skel[self.bone_name])
        self.assertEqual(["foo", "bar"], skel[self.bone_name][lang])
        self.assertIn("en", skel[self.bone_name])
        self.assertListEqual([], skel[self.bone_name]["en"])
        self.assertNotIn("fr", skel[self.bone_name])

    def test_singleValueFromClient(self):
        from viur.core.bones import TextBone
        from viur.core.bones import ReadFromClientError
        from viur.core.bones import ReadFromClientErrorSeverity
        bone = TextBone()
        skel = {}
        res = bone.singleValueFromClient("Foo", skel, self.bone_name, None)
        self.assertEqual(("Foo", None), res)
        res = bone.singleValueFromClient("", skel, self.bone_name, None)
        self.assertEqual(("", None), res)
        res = bone.singleValueFromClient(None, skel, self.bone_name, None)
        # self.assertEqual(("", None), res)
        self.assertIsInstance(res[1], list)
        self.assertTrue(res[1])  # list is not empty (hopefully contains a ReadFromClientError)
        self.assertIsInstance(rfce := res[1][0], ReadFromClientError)
        self.assertIs(ReadFromClientErrorSeverity.Invalid, rfce.severity)

    def test_getUniquePropertyIndexValues_single(self):
        from viur.core.bones import TextBone
        from viur.core.bones.base import UniqueValue, UniqueLockMethod
        bone = TextBone(unique=UniqueValue(UniqueLockMethod.SameValue, False, ""))
        result = bone.getUniquePropertyIndexValues({self.bone_name: "Hello"}, self.bone_name)
        self.assertEqual(1, len(result))
        self.assertTrue(result[0].startswith("S-"))

    def test_getUniquePropertyIndexValues_empty(self):
        from viur.core.bones import TextBone
        from viur.core.bones.base import UniqueValue, UniqueLockMethod
        bone = TextBone(unique=UniqueValue(UniqueLockMethod.SameValue, False, ""))
        self.assertEqual([], bone.getUniquePropertyIndexValues({self.bone_name: None}, self.bone_name))

    def test_getUniquePropertyIndexValues_languages(self):
        from viur.core.bones import TextBone
        from viur.core.bones.base import UniqueValue, UniqueLockMethod
        bone = TextBone(
            unique=UniqueValue(UniqueLockMethod.SameValue, False, ""),
            languages=["de", "en"],
        )
        result = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": "Hallo", "en": "Hello"}}, self.bone_name,
        )
        self.assertEqual(2, len(result))

    def test_getUniquePropertyIndexValues_languages_partial_none(self):
        from viur.core.bones import TextBone
        from viur.core.bones.base import UniqueValue, UniqueLockMethod
        bone = TextBone(
            unique=UniqueValue(UniqueLockMethod.SameValue, False, ""),
            languages=["de", "en"],
        )
        result = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": "Hallo", "en": None}}, self.bone_name,
        )
        self.assertEqual(1, len(result))

    def test_escape_html_requires_valid_html_none(self):
        from viur.core.bones import TextBone
        # The default validHtml (conf.bone_html_default_allow) conflicts with a disabled escaping
        with self.assertRaises(ValueError):
            TextBone(escape_html=False)
        # ... an explicitly given validHtml as well
        with self.assertRaises(ValueError):
            TextBone(validHtml={"validTags": ["b"]}, escape_html=False)
        # Only the plain-text mode may skip the sanitizer
        TextBone(validHtml=None, escape_html=False)

    def test_escape_html_false_keeps_value_raw(self):
        from viur.core.bones import TextBone
        bone = TextBone(validHtml=None, escape_html=False)
        skel = {}
        client_value = 'line 1 with <b>bold</b> and a < b\nline 2 with "quotes" and \'apostrophes\'\nline 3'
        res = bone.singleValueFromClient(client_value, skel, self.bone_name, None)
        self.assertEqual((client_value, None), res)

    def test_escape_html_false_still_validates(self):
        from viur.core.bones import TextBone
        from viur.core.bones import ReadFromClientError, ReadFromClientErrorSeverity
        bone = TextBone(validHtml=None, escape_html=False, max_length=5)
        skel = {}
        # None is still rejected
        value, errors = bone.singleValueFromClient(None, skel, self.bone_name, None)
        self.assertEqual("", value)
        self.assertIsInstance(rfce := errors[0], ReadFromClientError)
        self.assertIs(ReadFromClientErrorSeverity.Invalid, rfce.severity)
        # max_length is still enforced
        value, errors = bone.singleValueFromClient("too long", skel, self.bone_name, None)
        self.assertEqual("", value)
        self.assertIsInstance(errors[0], ReadFromClientError)

    def test_escape_html_false_tracks_no_blobs(self):
        from viur.core.bones import TextBone
        bone = TextBone(validHtml=None, escape_html=False)
        skel = {self.bone_name: '<img src="/file/download/some-dlkey">'}
        self.assertEqual(set(), bone.getReferencedBlobs(skel, self.bone_name))

    def test_refresh_unescapes(self):
        from viur.core.bones import TextBone
        bone = TextBone(validHtml=None, escape_html=False)
        skel = {self.bone_name: "a &lt; b and &quot;quoted&quot;"}
        bone.refresh(skel, self.bone_name)
        self.assertEqual('a < b and "quoted"', skel[self.bone_name])

    def test_refresh_unescapes_multiple(self):
        from viur.core.bones import TextBone
        bone = TextBone(validHtml=None, escape_html=False, multiple=True)
        skel = {self.bone_name: ["a &lt; b", "c &gt; d"]}
        bone.refresh(skel, self.bone_name)
        self.assertEqual(["a < b", "c > d"], skel[self.bone_name])

    def test_refresh_unescapes_languages(self):
        from viur.core.bones import TextBone
        bone = TextBone(validHtml=None, escape_html=False, languages=["de", "en"])
        skel = {self.bone_name: {"de": "a &lt; b", "en": "c &gt; d"}}
        bone.refresh(skel, self.bone_name)
        self.assertEqual({"de": "a < b", "en": "c > d"}, skel[self.bone_name])

    def test_refresh_keeps_value_when_escaping(self):
        from viur.core.bones import TextBone
        bone = TextBone()
        skel = {self.bone_name: "a &lt; b"}
        bone.refresh(skel, self.bone_name)
        self.assertEqual("a &lt; b", skel[self.bone_name])

    def test_structure_contains_escape_html(self):
        from viur.core.bones import TextBone
        self.assertTrue(TextBone().structure()["escape_html"])
        self.assertFalse(TextBone(validHtml=None, escape_html=False).structure()["escape_html"])

    def test_html_parsing(self):
        from viur.core.bones import TextBone
        bone = TextBone()
        skel = {}

        client_value = """
<h1>Headline</h1>
<p>This is a&nbsp;paragraph<br>
Next line</p>
<script>alert('I am evil!')</script>
<img onload="alert('I am evil!')" src="/logo.png">
<div>A div</div>
<div>
    Another div
    <span>Opened span, but never closed
</div>
"""
        res = bone.singleValueFromClient(client_value, skel, self.bone_name, None)
        escaped_value = (
            """<h1>Headline</h1>"""
            """<p>This is a&nbsp;paragraph<br>"""
            """Next line</p>"""
            """ alert(&#39;I am evil!&#39;)"""
            """<img src="/logo.png"><div>A div</div>"""
            """<div>    Another div    <span>Opened span, but never closed</span></div>"""
        )
        self.assertEqual((escaped_value, None), res)
