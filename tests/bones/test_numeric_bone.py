import unittest

LARGE_INT = 123_465 * 10 ** 12
LARGE_FLOAT = 123_465.0 * 10 ** 12
SMALL_FLOAT = 123_465.0 * 10 ** -12


class TestNumericBone(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from main import monkey_patch
        monkey_patch()

    def test_isEmpty_default_bone(self):
        from viur.core.bones import NumericBone
        self._run_tests(NumericBone())

    def test_isEmpty_emptyNone(self):
        from viur.core.bones import NumericBone
        self._run_tests(NumericBone(getEmptyValueFunc=lambda: None))

    def test_isEmpty_precision(self):
        from viur.core.bones import NumericBone
        self._run_tests(NumericBone(precision=2))

    def test_isEmpty_precision_emptyNone(self):
        from viur.core.bones import NumericBone
        self._run_tests(NumericBone(precision=2, getEmptyValueFunc=lambda: None))

    def _run_tests(self, bone):
        self.assertFalse(bone.isEmpty(123))
        self.assertFalse(bone.isEmpty("123"))
        self.assertFalse(bone.isEmpty("123.456"))
        self.assertFalse(bone.isEmpty("123,456"))
        self.assertFalse(bone.isEmpty(123.456))
        self.assertFalse(bone.isEmpty(LARGE_INT))
        self.assertFalse(bone.isEmpty(LARGE_FLOAT))
        if bone.precision != 0:
            self.assertFalse(bone.isEmpty(SMALL_FLOAT), msg=vars(bone))

        self.assertTrue(bone.isEmpty(""))
        self.assertTrue(bone.isEmpty(None))
        self.assertTrue(bone.isEmpty([]))
        self.assertTrue(bone.isEmpty(bone.getEmptyValue()))
        self.assertTrue(bone.isEmpty(str(bone.getEmptyValue())))
        if bone.getEmptyValue() is not None:
            self.assertTrue(bone.isEmpty(float(bone.getEmptyValue())))
            self.assertTrue(bone.isEmpty(int(bone.getEmptyValue())))

    def test_convert_to_numeric(self):
        from viur.core.bones import NumericBone
        bone = NumericBone(precision=2)
        self.assertEqual(42.0, bone._convert_to_numeric(42))
        self.assertEqual(42.4, bone._convert_to_numeric(42.4))
        self.assertEqual(42.6, bone._convert_to_numeric(42.6))
        self.assertEqual(42.6, bone._convert_to_numeric("42.6"))
        self.assertEqual(42.6, bone._convert_to_numeric("42,6"))
        self.assertIsInstance(bone._convert_to_numeric(42), float)
        with self.assertRaises(TypeError):
            bone._convert_to_numeric(None)
        with self.assertRaises(ValueError):
            bone._convert_to_numeric("xyz")
        with self.assertRaises(ValueError):
            bone._convert_to_numeric("1.2.3")

        bone = NumericBone(precision=0)
        self.assertEqual(42, bone._convert_to_numeric(42))
        self.assertEqual(42, bone._convert_to_numeric(42.4))
        self.assertEqual(42, bone._convert_to_numeric(42.6))
        self.assertEqual(42, bone._convert_to_numeric(42.0))
        self.assertEqual(42, bone._convert_to_numeric("42.6"))
        self.assertEqual(42, bone._convert_to_numeric("42,6"))
        with self.assertRaises(ValueError):
            bone._convert_to_numeric("123.456,5")
        self.assertIsInstance(bone._convert_to_numeric(42), int)


class TestNumericBone_fromClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from main import monkey_patch
        monkey_patch()
        cls.bone_name = "my_numeric_bone"

    def test_fromClient_int(self):
        from viur.core.bones import NumericBone
        from viur.core.bones.base import ReadFromClientError
        bone = NumericBone(precision=0)
        skel = {}
        # okay: int as str
        data = {self.bone_name: "1234"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], int)
        # okay: large int as str
        data = {self.bone_name: str(LARGE_INT)}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(LARGE_INT, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], int)
        # okay: int as int
        data = {self.bone_name: 1234}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], int)
        # okay: large int as int
        data = {self.bone_name: LARGE_INT}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(LARGE_INT, skel[self.bone_name])
        # invalid: precision=0 allows only ints
        data = {self.bone_name: "1234.0"}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)
        # invalid data
        data = {self.bone_name: ""}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)
        # invalid data
        data = {self.bone_name: None}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)
        # invalid data
        data = {self.bone_name: "abc"}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)
        # invalid data: too large
        data = {self.bone_name: 10 ** 20}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)
        # invalid data: too small
        data = {self.bone_name: -10 ** 20}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)

    def test_fromClient_float(self):
        from viur.core.bones import NumericBone
        from viur.core.bones.base import ReadFromClientError
        bone = NumericBone(precision=8)
        skel = {}
        # okay: int as str
        data = {self.bone_name: "1234"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234.0, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
        # okay: float as str
        data = {self.bone_name: "1234.5"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234.5, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
        # okay: float as str with comma
        data = {self.bone_name: "1234,5"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234.5, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
        # okay: large int as str
        data = {self.bone_name: str(LARGE_INT)}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(LARGE_INT, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
        # okay: large float as str
        data = {self.bone_name: str(LARGE_FLOAT)}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(LARGE_INT, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
        # okay: int as int
        data = {self.bone_name: 1234}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234.0, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
        # okay: float as float
        data = {self.bone_name: 1234.5}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234.5, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
        # invalid data
        data = {self.bone_name: ""}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)
        # invalid data
        data = {self.bone_name: None}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)
        # invalid data
        data = {self.bone_name: "abc"}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)
        # invalid data: too large
        data = {self.bone_name: 10.0 ** 20}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)
        # invalid data: too small
        data = {self.bone_name: -10.0 ** 20}
        self.assertIsInstance(res := bone.fromClient(skel, self.bone_name, data), list)
        self.assertTrue(res)  # list not empty
        self.assertIsInstance(res[0], ReadFromClientError)

        # tests where the provided values has a higher precision
        bone = NumericBone(precision=2)
        skel = {}
        # okay: float as str
        data = {self.bone_name: "1234.56789"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234.57, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
        # okay: float as float
        data = {self.bone_name: 1234.56789}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234.57, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
        # okay: float as float, force to round down
        data = {self.bone_name: 1234.56289}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))  # None = no error
        self.assertIn(self.bone_name, skel)
        self.assertEqual(1234.56, skel[self.bone_name])
        self.assertIsInstance(skel[self.bone_name], float)
