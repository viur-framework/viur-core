import unittest


class TestUriBone(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from main import monkey_patch
        monkey_patch()
        cls.bone_name = "uriTestBone"

    def is_invalid(self, res, url_value):
        from viur.core.bones import ReadFromClientError, ReadFromClientErrorSeverity
        self.assertEqual(url_value, res[0])
        self.assertIsInstance(res[1], list)
        self.assertTrue(res[1])  # list is not empty (hopefully contains a ReadFromClientError)
        self.assertIsInstance(rfce := res[1][0], ReadFromClientError)
        self.assertIs(ReadFromClientErrorSeverity.Invalid, rfce.severity)

    def test_singleValueFromClient(self):
        from viur.core.bones import UriBone
        # Test for protocol
        bone = UriBone(accepted_protocols=["http*"])
        skel = {}
        url_value = "https://www.viur.dev/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "http://www.viur.dev/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "file://www.viur.dev/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)

        # Test for ports
        bone = UriBone(accepted_ports=["1-10", "15", 20])
        url_value = "http://localhost:1"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "http://localhost:15"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "http://localhost:20"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "http://localhost:21"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)

        # Test domain_allowed_list
        bone = UriBone(domain_allowed_list=["viur.dev"])
        url_value = "https://www.viur.dev/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "https://foo.viur.dev/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "https://viur.com/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)

        # Test for fnmatch in domain_allowed_list
        bone = UriBone(domain_allowed_list=["w*.viur.dev"])
        url_value = "https://www.viur.dev/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "https://www2.viur.dev/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "https://foo.viur.dev/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)
        url_value = "https://viur.dev/"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)

        # Test for clean_get_params
        bone = UriBone(clean_get_params=False)
        url_value = "https://www.viur.dev/?foo=bar"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)

        bone = UriBone(clean_get_params=True)
        url_value = "https://www.viur.dev/?foo=bar"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual(("https://www.viur.dev/", None), res)

        # Test for local_path_allowed
        bone = UriBone(local_path_allowed=True)
        url_value = "/foo/bar/?a=b"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        url_value = "foo/bar/?a=b"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual(("/foo/bar/?a=b", None), res)

        bone = UriBone(local_path_allowed=False)
        url_value = "/foo/bar/?a=b"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)

        # Test for general schema, not valid URLs
        bone = UriBone()
        skel = {}
        url_value = "foo"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)
        #
        url_value = "foo/bar"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)
        #
        url_value = "foo:/bar"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
        #
        url_value = "foo/:bar"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)
        #
        url_value = "foo//:bar"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.is_invalid(res, url_value)
        #
        url_value = "http://https://viur.dev"
        res = bone.singleValueFromClient(url_value, skel, self.bone_name, None)
        self.assertEqual((url_value, None), res)
