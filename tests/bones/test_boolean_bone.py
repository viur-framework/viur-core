from abstract import ViURTestCase


class TestBooleanBoneInit(ViURTestCase):

    def test_default_is_none(self):
        from viur.core.bones.boolean import BooleanBone
        bone = BooleanBone()
        self.assertIsNone(bone.defaultValue)

    def test_default_true(self):
        from viur.core.bones.boolean import BooleanBone
        bone = BooleanBone(defaultValue=True)
        self.assertTrue(bone.defaultValue)

    def test_default_false(self):
        from viur.core.bones.boolean import BooleanBone
        bone = BooleanBone(defaultValue=False)
        self.assertFalse(bone.defaultValue)

    def test_invalid_default_raises(self):
        from viur.core.bones.boolean import BooleanBone
        with self.assertRaises(TypeError):
            BooleanBone(defaultValue="yes")

    def test_multiple_raises(self):
        from viur.core.bones.boolean import BooleanBone
        with self.assertRaises(ValueError):
            BooleanBone(multiple=True)

    def test_callable_default(self):
        from viur.core.bones.boolean import BooleanBone
        bone = BooleanBone(defaultValue=lambda self, skel: True)
        self.assertTrue(callable(bone.defaultValue))


class TestBooleanBoneIsEmpty(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core.bones.boolean import BooleanBone
        self.bone = BooleanBone()

    def test_false_is_empty(self):
        self.assertTrue(self.bone.isEmpty(False))

    def test_none_is_empty(self):
        self.assertTrue(self.bone.isEmpty(None))

    def test_zero_is_empty(self):
        self.assertTrue(self.bone.isEmpty(0))

    def test_empty_string_is_empty(self):
        self.assertTrue(self.bone.isEmpty(""))

    def test_true_is_not_empty(self):
        self.assertFalse(self.bone.isEmpty(True))

    def test_one_is_not_empty(self):
        self.assertFalse(self.bone.isEmpty(1))


class TestBooleanBoneSingleValueFromClient(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core.bones.boolean import BooleanBone
        self.bone = BooleanBone()

    def _from_client(self, value):
        val, err = self.bone.singleValueFromClient(value, {}, "flag", {})
        self.assertIsNone(err)
        return val

    def test_true_string(self):
        self.assertTrue(self._from_client("true"))

    def test_false_string(self):
        self.assertFalse(self._from_client("false"))

    def test_one_string(self):
        self.assertTrue(self._from_client("1"))

    def test_zero_string(self):
        self.assertFalse(self._from_client("0"))


class TestBooleanBoneSetBoneValue(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core.bones.boolean import BooleanBone
        self.bone = BooleanBone()

    def test_set_true(self):
        skel = {}
        result = self.bone.setBoneValue(skel, "flag", True, False)
        self.assertTrue(result)
        self.assertTrue(skel["flag"])

    def test_set_false(self):
        skel = {}
        result = self.bone.setBoneValue(skel, "flag", False, False)
        self.assertTrue(result)
        self.assertFalse(skel["flag"])

    def test_append_raises(self):
        with self.assertRaises(ValueError):
            self.bone.setBoneValue({}, "flag", True, True)


class TestBooleanBoneSetBoneValueRespectsConfig(ViURTestCase):
    """setBoneValue must honour conf.bone_boolean_str2true like every other path in the bone."""

    def setUp(self):
        super().setUp()
        from viur.core import conf
        from viur.core.bones.boolean import BooleanBone
        self.bone = BooleanBone()
        self._original = conf.bone_boolean_str2true
        conf.bone_boolean_str2true = ("ja", "true", "yes", "1")

    def tearDown(self):
        from viur.core import conf
        conf.bone_boolean_str2true = self._original
        super().tearDown()

    def test_custom_truthy_value(self):
        skel = {}
        self.assertTrue(self.bone.setBoneValue(skel, "flag", "ja", False))
        self.assertTrue(skel["flag"])

    def test_custom_truthy_value_with_language(self):
        from viur.core.bones.boolean import BooleanBone
        bone = BooleanBone(languages=["de", "en"])
        skel = {"flag": {}}
        self.assertTrue(bone.setBoneValue(skel, "flag", "ja", False, "de"))
        self.assertTrue(skel["flag"]["de"])

    def test_unknown_value_stays_false(self):
        skel = {}
        self.assertTrue(self.bone.setBoneValue(skel, "flag", "nope", False))
        self.assertFalse(skel["flag"])


class TestBooleanBoneRefresh(ViURTestCase):
    """refresh() runs on raw datastore values, which may still be None."""

    def test_refresh_multilang_with_none_value(self):
        """An entity written before the bone existed has no value at all; the defaults must apply."""
        from viur.core.bones.boolean import BooleanBone
        bone = BooleanBone(languages=["de", "en"])
        bone.name = "flag"
        skel = {"flag": None}
        bone.refresh(skel, "flag")
        self.assertEqual({"de": None, "en": None}, skel["flag"])

    def test_refresh_multilang_normalizes_strings(self):
        from viur.core.bones.boolean import BooleanBone
        bone = BooleanBone(languages=["de", "en"])
        bone.name = "flag"
        skel = {"flag": {"de": "true", "en": "false"}}
        bone.refresh(skel, "flag")
        self.assertEqual({"de": True, "en": False}, skel["flag"])

    def test_refresh_multilang_fills_missing_language(self):
        from viur.core.bones.boolean import BooleanBone
        bone = BooleanBone(languages=["de", "en"], defaultValue=True)
        bone.name = "flag"
        skel = {"flag": {"de": "1"}}
        bone.refresh(skel, "flag")
        self.assertEqual({"de": True, "en": True}, skel["flag"])
