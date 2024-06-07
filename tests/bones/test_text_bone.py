import unittest

import mock


class TestTextBone_fromClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from main import monkey_patch
        monkey_patch()
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
