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
