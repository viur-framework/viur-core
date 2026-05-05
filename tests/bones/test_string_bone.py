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


class TestStringBone_getUniquePropertyIndexValues(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "myStringBone"

    def _make_bone(self, **kwargs):
        from viur.core.bones import StringBone
        from viur.core.bones.base import UniqueValue, UniqueLockMethod
        return StringBone(unique=UniqueValue(UniqueLockMethod.SameValue, False, ""), **kwargs)

    def _make_bone_sameset(self, **kwargs):
        from viur.core.bones import StringBone
        from viur.core.bones.base import UniqueValue, UniqueLockMethod
        return StringBone(unique=UniqueValue(UniqueLockMethod.SameSet, False, ""), **kwargs)

    # --- empty / None ---

    def test_empty_value_returns_empty_list(self):
        bone = self._make_bone()
        self.assertEqual([], bone.getUniquePropertyIndexValues({self.bone_name: None}, self.bone_name))

    def test_empty_value_languages_returns_empty_list(self):
        bone = self._make_bone(languages=["de", "en"])
        self.assertEqual([], bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": None, "en": None}}, self.bone_name,
        ))

    def test_partial_language_none_skipped(self):
        bone = self._make_bone(languages=["de", "en"])
        result = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": "Hallo", "en": None}}, self.bone_name,
        )
        self.assertEqual(1, len(result))

    # --- single, no languages ---

    def test_single_value_produces_one_hash(self):
        bone = self._make_bone()
        result = bone.getUniquePropertyIndexValues({self.bone_name: "Hello"}, self.bone_name)
        self.assertEqual(1, len(result))
        self.assertTrue(result[0].startswith("S-"))

    def test_single_case_sensitive_distinct(self):
        bone = self._make_bone(caseSensitive=True)
        r_upper = bone.getUniquePropertyIndexValues({self.bone_name: "Hello"}, self.bone_name)
        r_lower = bone.getUniquePropertyIndexValues({self.bone_name: "hello"}, self.bone_name)
        self.assertNotEqual(r_upper, r_lower)

    def test_single_case_insensitive_normalizes(self):
        bone = self._make_bone(caseSensitive=False)
        r1 = bone.getUniquePropertyIndexValues({self.bone_name: "Hello"}, self.bone_name)
        r2 = bone.getUniquePropertyIndexValues({self.bone_name: "HELLO"}, self.bone_name)
        r3 = bone.getUniquePropertyIndexValues({self.bone_name: "hello"}, self.bone_name)
        self.assertEqual(r1, r2)
        self.assertEqual(r1, r3)

    # --- single, with languages ---

    def test_languages_produces_one_hash_per_language(self):
        bone = self._make_bone(languages=["de", "en"])
        result = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": "Hallo", "en": "Hello"}}, self.bone_name,
        )
        self.assertEqual(2, len(result))

    def test_languages_case_insensitive_normalizes(self):
        bone = self._make_bone(languages=["de", "en"], caseSensitive=False)
        r1 = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": "Hallo", "en": "Hello"}}, self.bone_name,
        )
        r2 = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": "HALLO", "en": "HELLO"}}, self.bone_name,
        )
        self.assertEqual(r1, r2)

    def test_languages_case_sensitive_distinct(self):
        bone = self._make_bone(languages=["de", "en"], caseSensitive=True)
        r1 = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": "Hallo", "en": "Hello"}}, self.bone_name,
        )
        r2 = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": "HALLO", "en": "HELLO"}}, self.bone_name,
        )
        self.assertNotEqual(r1, r2)

    # --- multiple, no languages ---

    def test_multiple_samevalue_produces_one_hash_per_entry(self):
        bone = self._make_bone(multiple=True)
        result = bone.getUniquePropertyIndexValues({self.bone_name: ["Foo", "Bar", "Baz"]}, self.bone_name)
        self.assertEqual(3, len(result))

    def test_multiple_sameset_produces_one_combined_hash(self):
        bone = self._make_bone_sameset(multiple=True)
        result = bone.getUniquePropertyIndexValues({self.bone_name: ["Foo", "Bar"]}, self.bone_name)
        self.assertEqual(1, len(result))

    def test_multiple_sameset_order_independent(self):
        bone = self._make_bone_sameset(multiple=True)
        r1 = bone.getUniquePropertyIndexValues({self.bone_name: ["Foo", "Bar"]}, self.bone_name)
        r2 = bone.getUniquePropertyIndexValues({self.bone_name: ["Bar", "Foo"]}, self.bone_name)
        self.assertEqual(r1, r2)

    # --- multiple, with languages ---

    def test_multiple_languages_flattens_all_values(self):
        bone = self._make_bone(multiple=True, languages=["de", "en"])
        result = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": ["Foo", "Bar"], "en": ["Baz"]}}, self.bone_name,
        )
        self.assertEqual(3, len(result))

    def test_multiple_languages_empty_lang_skipped(self):
        bone = self._make_bone(multiple=True, languages=["de", "en"])
        result = bone.getUniquePropertyIndexValues(
            {self.bone_name: {"de": ["Foo"], "en": []}}, self.bone_name,
        )
        self.assertEqual(1, len(result))
