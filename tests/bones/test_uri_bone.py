from abstract import ViURTestCase


class TestUriBone(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
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


class TestUriBoneAcceptedProtocols(ViURTestCase):
    """``accepted_protocols`` takes a single protocol, an iterable of them, or patterns.

    A plain string used to be turned into a set of its characters, which inverted the
    restriction: ``"https"`` allowed h, t, p and s but not https. The wildcard was then
    tested against the original argument, so for a string it was a substring test and any
    pattern containing a ``*`` switched the protocol check off altogether.
    """

    @staticmethod
    def _bone(accepted_protocols):
        from viur.core.bones import UriBone
        return UriBone(accepted_protocols=accepted_protocols)

    def _accepts(self, bone, url) -> bool:
        return bone.isInvalid(url) is None

    def test_string_is_one_protocol(self):
        bone = self._bone("https")
        self.assertEqual({"https"}, bone.accepted_protocols)
        self.assertTrue(self._accepts(bone, "https://www.viur.dev/"))
        self.assertFalse(self._accepts(bone, "http://www.viur.dev/"))

    def test_string_pattern_stays_a_pattern(self):
        bone = self._bone("http*")
        self.assertEqual({"http*"}, bone.accepted_protocols)
        self.assertTrue(self._accepts(bone, "http://www.viur.dev/"))
        self.assertTrue(self._accepts(bone, "https://www.viur.dev/"))
        # The point of the restriction: a pattern must not allow everything
        self.assertFalse(self._accepts(bone, "file://etc/passwd"))

    def test_iterable_is_normalized_to_a_set(self):
        bone = self._bone(["http", "https"])
        self.assertEqual({"http", "https"}, bone.accepted_protocols)
        self.assertTrue(self._accepts(bone, "http://www.viur.dev/"))
        self.assertFalse(self._accepts(bone, "ftp://www.viur.dev/"))

    def test_bare_wildcard_string_allows_everything(self):
        bone = self._bone("*")
        self.assertIsNone(bone.accepted_protocols)
        self.assertTrue(self._accepts(bone, "file://etc/passwd"))

    def test_bare_wildcard_in_an_iterable_allows_everything(self):
        bone = self._bone(["http", "*"])
        self.assertIsNone(bone.accepted_protocols)
        self.assertTrue(self._accepts(bone, "file://etc/passwd"))

    def test_no_restriction_by_default(self):
        bone = self._bone(None)
        self.assertIsNone(bone.accepted_protocols)
        self.assertTrue(self._accepts(bone, "file://etc/passwd"))

    def test_non_iterable_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._bone(5)
