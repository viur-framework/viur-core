from abstract import ViURTestCase


class TestStringBone(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "myStringBone"

    def test_isEmpty_default_bone(self):
        from viur.core.bones import StringBone
        self._run_tests(bone := StringBone(descr="empty_str"))
        self.assertEqual("", bone.getEmptyValue())
        self.assertIsNone(bone.defaultValue)

    def _run_tests(self, bone):
        # print(bone)
        self.assertFalse(bone.isEmpty(123))
        self.assertFalse(bone.isEmpty("123"))

        self.assertTrue(bone.isEmpty(""))
        self.assertTrue(bone.isEmpty(None))
        self.assertTrue(bone.isEmpty([]))
        self.assertTrue(bone.isEmpty(bone.getEmptyValue()))
        self.assertTrue(bone.isEmpty(str(bone.getEmptyValue())))


class TestStringBone_setBoneValue(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "myStringBone"

    def test_setBoneValue_single(self):
        from viur.core.bones import StringBone
        bone = StringBone()
        skel = {}
        self.assertTrue(bone.setBoneValue(skel, self.bone_name, value := "foo", False, None))
        self.assertIn(self.bone_name, skel)
        self.assertEqual(value, skel[self.bone_name])
        # Don't append on multiple bones
        self.assertFalse(bone.multiple)
        with self.assertRaises(AssertionError):
            bone.setBoneValue(skel, self.bone_name, "foo", True, None)
        # Fail with language
        self.assertIsNone(bone.languages)
        with self.assertRaises(AssertionError):
            bone.setBoneValue(skel, self.bone_name, "foo", False, "en")

    def test_setBoneValue_multi(self):
        from viur.core.bones import StringBone
        bone = StringBone(multiple=True)
        skel = {}
        self.assertTrue(bone.setBoneValue(skel, self.bone_name, value := ["foo"], False, None))
        self.assertIn(self.bone_name, skel)
        self.assertListEqual(value, skel[self.bone_name])
        # Append
        self.assertTrue(bone.multiple)
        self.assertTrue(bone.setBoneValue(skel, self.bone_name, "bar", True, None))
        self.assertEqual(["foo", "bar"], skel[self.bone_name])
        # self.assertIs(value, skel[self.bone_name])
        bone.setBoneValue(skel, self.bone_name, "foo", True, None)
        # Fail with language
        self.assertIsNone(bone.languages)
        with self.assertRaises(AssertionError):
            bone.setBoneValue(skel, self.bone_name, "foo", False, "en")


class TestStringBone_fromClient(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "myStringBone"

    def test_fromClient_single(self):
        from viur.core.bones import StringBone
        from viur.core.bones.base import ReadFromClientError
        bone = StringBone()
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
        from viur.core.bones import StringBone
        bone = StringBone(multiple=True)
        skel = {}
        data = {self.bone_name: ["foo", "bar"]}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertIn(self.bone_name, skel)
        self.assertListEqual(data[self.bone_name], skel[self.bone_name])

    def test_fromClient_lang(self):
        from viur.core.bones import StringBone
        bone = StringBone(languages=["en", "de"])
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
        from viur.core.bones import StringBone
        bone = StringBone(multiple=True, languages=["en", "de"])
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
        from viur.core.bones import StringBone
        from viur.core.bones import ReadFromClientError
        from viur.core.bones import ReadFromClientErrorSeverity
        bone = StringBone()
        skel = {}
        # hint: StringBone has no specific isInvalid(), so every value is valid like in BaseBone
        res = bone.singleValueFromClient("Foo", skel, self.bone_name, None)
        self.assertEqual(("Foo", None), res)
        res = bone.singleValueFromClient("", skel, self.bone_name, None)
        self.assertEqual(("", None), res)
        res = bone.singleValueFromClient(None, skel, self.bone_name, None)
        self.assertEqual(("None", None), res)

        # Custom isInvalid function which checks for truthy values to test invalid case as well
        bone = StringBone(vfunc=lambda value: not value)
        res = bone.singleValueFromClient("Foo", skel, self.bone_name, None)
        self.assertEqual(("Foo", None), res)
        res = bone.singleValueFromClient("", skel, self.bone_name, None)
        self.assertEqual("", res[0])
        self.assertIsInstance(res[1], list)
        self.assertTrue(res[1])  # list is not empty (hopefully contains a ReadFromClientError)
        self.assertIsInstance(rfce := res[1][0], ReadFromClientError)
        self.assertIs(ReadFromClientErrorSeverity.Invalid, rfce.severity)


class TestStringBoneSerialize(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "myStringBone"

    def test_singleValueSerialize_caseSensitive(self):
        from viur.core.bones import StringBone
        bone = StringBone(caseSensitive=True)
        skel = {}
        res = bone.singleValueSerialize("Foo", skel, self.bone_name, True)
        self.assertEqual("Foo", res)
        res = bone.singleValueSerialize("Foo", skel, self.bone_name, False)
        self.assertEqual("Foo", res)
        res = bone.singleValueSerialize(None, skel, self.bone_name, True)
        self.assertEqual("", res)
        res = bone.singleValueSerialize(None, skel, self.bone_name, False)
        self.assertEqual("", res)

    def test_singleValueSerialize_caseInSensitive(self):
        from viur.core.bones import StringBone
        bone = StringBone(caseSensitive=False)
        skel = {}
        res = bone.singleValueSerialize("Foo", skel, self.bone_name, True)
        self.assertDictEqual({"val": "Foo", "idx": "foo"}, res)
        res = bone.singleValueSerialize("Foo", skel, self.bone_name, False)
        self.assertEqual("Foo", res)
        res = bone.singleValueSerialize(None, skel, self.bone_name, True)
        self.assertDictEqual({"val": "", "idx": ""}, res)
        res = bone.singleValueSerialize(None, skel, self.bone_name, False)
        self.assertEqual("", res)

    def test_singleValueUnserialize(self):
        from viur.core.bones import StringBone
        bone = StringBone()
        res = bone.singleValueUnserialize({"val": "Foo", "idx": "foo"})
        self.assertEqual("Foo", res)
        res = bone.singleValueUnserialize({"idx": "foo"})
        self.assertEqual("{'idx': 'foo'}", res)  # TODO: Should a broken dict really be casted to a str?
        res = bone.singleValueUnserialize("Foo")
        self.assertEqual("Foo", res)
        res = bone.singleValueUnserialize(None)
        self.assertEqual("", res)


class TestStringBoneIsInvalid(ViURTestCase):

    def test_within_max_length(self):
        from viur.core.bones import StringBone
        bone = StringBone(max_length=10)
        self.assertIsNone(bone.isInvalid("hello"))

    def test_exceeds_max_length(self):
        from viur.core.bones import StringBone
        bone = StringBone(max_length=5)
        self.assertIsNotNone(bone.isInvalid("toolong"))

    def test_min_length_satisfied(self):
        from viur.core.bones import StringBone
        bone = StringBone(min_length=3)
        self.assertIsNone(bone.isInvalid("abc"))

    def test_min_length_not_reached(self):
        from viur.core.bones import StringBone
        bone = StringBone(min_length=5)
        self.assertIsNotNone(bone.isInvalid("ab"))

    def test_max_length_none_no_limit(self):
        from viur.core.bones import StringBone
        bone = StringBone(max_length=None)
        self.assertIsNone(bone.isInvalid("x" * 10_000))


class TestStringBoneInit(ViURTestCase):

    def test_invalid_max_length_zero_raises(self):
        from viur.core.bones import StringBone
        with self.assertRaises(ValueError):
            StringBone(max_length=0)

    def test_invalid_min_length_zero_raises(self):
        from viur.core.bones import StringBone
        with self.assertRaises(ValueError):
            StringBone(min_length=0)

    def test_min_greater_than_max_raises(self):
        from viur.core.bones import StringBone
        with self.assertRaises(ValueError):
            StringBone(min_length=10, max_length=5)


class TestStringBoneTypeCoerce(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core.bones import StringBone
        self.bone = StringBone()

    def test_string_passthrough(self):
        self.assertEqual("hello", self.bone.type_coerce_single_value("hello"))

    def test_int_to_string(self):
        self.assertEqual("42", self.bone.type_coerce_single_value(42))

    def test_float_to_string(self):
        self.assertEqual("3.14", self.bone.type_coerce_single_value(3.14))

    def test_none_returns_empty(self):
        self.assertEqual("", self.bone.type_coerce_single_value(None))

    def test_datetime_to_iso(self):
        import datetime
        dt = datetime.datetime(2024, 1, 15, 12, 0, 0)
        result = self.bone.type_coerce_single_value(dt)
        self.assertIn("2024-01-15", result)

    def test_unsupported_type_raises(self):
        with self.assertRaises(ValueError):
            self.bone.type_coerce_single_value(object())


class TestStringBoneSingleValueFromClientEscape(ViURTestCase):

    def test_html_escaped_by_default(self):
        from viur.core.bones import StringBone
        bone = StringBone()
        val, err = bone.singleValueFromClient("<b>bold</b>", {}, "txt", {})
        self.assertIsNone(err)
        self.assertIn("&lt;", val)

    def test_no_escape_when_disabled(self):
        from viur.core.bones import StringBone
        bone = StringBone(escape_html=False)
        val, err = bone.singleValueFromClient("<b>bold</b>", {}, "txt", {})
        self.assertIsNone(err)
        self.assertEqual("<b>bold</b>", val)

    def test_max_length_exceeded_no_escape_returns_error(self):
        from viur.core.bones import StringBone
        # isInvalid() rejects over-length values before truncation happens
        bone = StringBone(max_length=5, escape_html=False)
        val, err = bone.singleValueFromClient("abcdefgh", {}, "txt", {})
        self.assertIsNotNone(err)
        self.assertEqual("", val)
