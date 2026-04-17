from abstract import ViURTestCase

LARGE_INT = 123_465 * 10 ** 12
LARGE_FLOAT = 123_465.0 * 10 ** 12
SMALL_FLOAT = 123_465.0 * 10 ** -12


class TestNumericBone(ViURTestCase):

    def test_isEmpty_default_bone(self):
        from viur.core.bones import NumericBone
        self._run_tests(bone := NumericBone())
        self.assertTrue(bone.isEmpty(SMALL_FLOAT), msg=vars(bone))

    def test_isEmpty_emptyNone(self):
        from viur.core.bones import NumericBone
        self._run_tests(bone := NumericBone(getEmptyValueFunc=lambda: None))
        self.assertFalse(bone.isEmpty(SMALL_FLOAT), msg=vars(bone))

    def test_isEmpty_precision(self):
        from viur.core.bones import NumericBone
        self._run_tests(bone := NumericBone(precision=2))
        self.assertTrue(bone.isEmpty(SMALL_FLOAT), msg=vars(bone))

    def test_isEmpty_high_precision(self):
        from viur.core.bones import NumericBone
        self._run_tests(bone := NumericBone(precision=8))
        self.assertFalse(bone.isEmpty(SMALL_FLOAT), msg=vars(bone))

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
        self.assertEqual(42.6, bone._convert_to_numeric({"val": "42,6", "idx": "42,6"}))
        self.assertIsInstance(bone._convert_to_numeric(42), float)
        with self.assertRaises(TypeError):
            bone._convert_to_numeric(None)
        with self.assertRaises(ValueError):
            bone._convert_to_numeric("xyz")
        with self.assertRaises(ValueError):
            bone._convert_to_numeric("1.2.3")
        # rounding
        self.assertEqual(42.12, bone._convert_to_numeric(42.1234))
        self.assertEqual(42.0, bone._convert_to_numeric(42.00001))
        self.assertEqual(42.07, bone._convert_to_numeric(42.066))
        self.assertEqual(42.06, bone._convert_to_numeric(42.064))

        bone = NumericBone(precision=0)
        self.assertEqual(42, bone._convert_to_numeric(42))
        self.assertEqual(42, bone._convert_to_numeric(42.4))
        self.assertEqual(42, bone._convert_to_numeric(42.6))
        self.assertEqual(42, bone._convert_to_numeric(42.0))
        self.assertEqual(42, bone._convert_to_numeric("42.6"))
        self.assertEqual(42, bone._convert_to_numeric("42,6"))
        self.assertEqual(42, bone._convert_to_numeric({"val": "42,6", "idx": "42,6"}))
        self.assertEqual(42, bone._convert_to_numeric({"val": "42", "idx": "42"}))
        with self.assertRaises(ValueError):
            bone._convert_to_numeric("123.456,5")
        self.assertIsInstance(bone._convert_to_numeric(42), int)


class TestNumericBone_fromClient(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
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


class TestNumericBone_Decimal(ViURTestCase):
    """Tests for NumericBone with decimal=True mode."""

    def test_decimal_flag(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        self.assertTrue(bone.decimal)
        self.assertEqual(bone._quantize_exp, Decimal("0.01"))

    def test_getEmptyValue_decimal(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        empty = bone.getEmptyValue()
        self.assertIsInstance(empty, Decimal)
        self.assertEqual(empty, Decimal("0.00"))

    def test_getEmptyValue_decimal_precision0(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=0, decimal=True)
        self.assertEqual(bone.getEmptyValue(), Decimal("0"))

    def test_getEmptyValue_decimal_precision4(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=4, decimal=True)
        self.assertEqual(bone.getEmptyValue(), Decimal("0.0000"))

    def test_isEmpty_decimal(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        self.assertTrue(bone.isEmpty(Decimal("0")))
        self.assertTrue(bone.isEmpty(Decimal("0.00")))
        self.assertTrue(bone.isEmpty(0))
        self.assertTrue(bone.isEmpty(0.0))
        self.assertTrue(bone.isEmpty("0"))
        self.assertTrue(bone.isEmpty("0.00"))
        self.assertTrue(bone.isEmpty(""))
        self.assertTrue(bone.isEmpty(None))
        self.assertFalse(bone.isEmpty(Decimal("1.00")))
        self.assertFalse(bone.isEmpty(Decimal("0.01")))
        self.assertFalse(bone.isEmpty("123.45"))
        self.assertFalse(bone.isEmpty(42))

    def test_to_decimal_conversions(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        self.assertEqual(bone._to_decimal("1234.56"), Decimal("1234.56"))
        self.assertEqual(bone._to_decimal(1234.56), Decimal("1234.56"))
        self.assertEqual(str(bone._to_decimal(1234.56)), "1234.56")
        self.assertEqual(bone._to_decimal(1234), Decimal("1234.00"))
        self.assertEqual(bone._to_decimal(Decimal("1234.567")), Decimal("1234.57"))
        self.assertIsNone(bone._to_decimal(None))

    def test_singleValueSerialize_decimal(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        result = bone.singleValueSerialize(Decimal("1234.56"), None, "amount", True)
        self.assertIsInstance(result, float)
        self.assertAlmostEqual(result, 1234.56)

    def test_singleValueSerialize_decimal_none(self):
        from viur.core.bones.numeric import NumericBone
        bone = NumericBone(precision=2, decimal=True)
        self.assertIsNone(bone.singleValueSerialize(None, None, "amount", True))

    def test_singleValueUnserialize_decimal_from_str(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        result = bone.singleValueUnserialize("1234.56")
        self.assertIsInstance(result, Decimal)
        self.assertEqual(result, Decimal("1234.56"))

    def test_singleValueUnserialize_decimal_from_float(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        result = bone.singleValueUnserialize(1234.56)
        self.assertIsInstance(result, Decimal)
        self.assertEqual(str(result), "1234.56")

    def test_singleValueUnserialize_decimal_from_int(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        result = bone.singleValueUnserialize(1234)
        self.assertEqual(result, Decimal("1234.00"))

    def test_singleValueUnserialize_decimal_none(self):
        from viur.core.bones.numeric import NumericBone
        bone = NumericBone(precision=2, decimal=True)
        self.assertIsNone(bone.singleValueUnserialize(None))

    def test_structure_decimal(self):
        from viur.core.bones.numeric import NumericBone
        bone = NumericBone(precision=2, decimal=True)
        s = bone.structure()
        self.assertTrue(s.get("decimal"))
        self.assertEqual(s["precision"], 2)

    def test_structure_no_decimal_flag_when_false(self):
        from viur.core.bones.numeric import NumericBone
        bone = NumericBone(precision=2)
        s = bone.structure()
        self.assertNotIn("decimal", s)


class TestNumericBone_Decimal_fromClient(ViURTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "amount"

    def test_fromClient_decimal_str(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        skel = {}
        data = {self.bone_name: "1234.56"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertIsInstance(skel[self.bone_name], Decimal)
        self.assertEqual(skel[self.bone_name], Decimal("1234.56"))

    def test_fromClient_decimal_comma(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        skel = {}
        data = {self.bone_name: "1234,56"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertEqual(skel[self.bone_name], Decimal("1234.56"))

    def test_fromClient_decimal_float(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        skel = {}
        data = {self.bone_name: 1234.56}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertIsInstance(skel[self.bone_name], Decimal)
        self.assertEqual(str(skel[self.bone_name]), "1234.56")

    def test_fromClient_decimal_int(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        skel = {}
        data = {self.bone_name: 1234}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertEqual(skel[self.bone_name], Decimal("1234.00"))

    def test_fromClient_decimal_rounding(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        skel = {}
        data = {self.bone_name: "1234.567"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertEqual(skel[self.bone_name], Decimal("1234.57"))

    def test_fromClient_decimal_zero(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        skel = {}
        data = {self.bone_name: 0}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertEqual(skel[self.bone_name], Decimal("0.00"))

    def test_fromClient_decimal_negative(self):
        from viur.core.bones.numeric import NumericBone
        from decimal import Decimal
        bone = NumericBone(precision=2, decimal=True)
        skel = {}
        data = {self.bone_name: "-99.99"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        self.assertEqual(skel[self.bone_name], Decimal("-99.99"))

    def test_fromClient_decimal_invalid(self):
        from viur.core.bones.numeric import NumericBone
        from viur.core.bones.base import ReadFromClientError
        bone = NumericBone(precision=2, decimal=True)
        skel = {}
        for invalid in ("abc", "", None):
            data = {self.bone_name: invalid}
            res = bone.fromClient(skel, self.bone_name, data)
            self.assertIsInstance(res, list, msg=f"Expected error for {invalid!r}")
            self.assertIsInstance(res[0], ReadFromClientError)

    def test_fromClient_decimal_minmax(self):
        from viur.core.bones.numeric import NumericBone
        from viur.core.bones.base import ReadFromClientError
        bone = NumericBone(precision=2, decimal=True, min=0, max=10000)
        skel = {}
        data = {self.bone_name: "5000.00"}
        self.assertIsNone(bone.fromClient(skel, self.bone_name, data))
        data = {self.bone_name: "-1"}
        self.assertIsInstance(bone.fromClient(skel, self.bone_name, data), list)
        data = {self.bone_name: "10001"}
        self.assertIsInstance(bone.fromClient(skel, self.bone_name, data), list)


class TestNumericBone_Decimal_Arithmetic(ViURTestCase):
    """Integration tests proving Decimal avoids float errors."""

    def test_no_float_accumulation_error(self):
        from decimal import Decimal
        values = [Decimal("0.10")] * 10
        self.assertEqual(sum(values), Decimal("1.00"))

    def test_tax_calculation(self):
        from decimal import Decimal, ROUND_HALF_UP
        subtotal = Decimal("1234.56")
        tax = (subtotal * Decimal("19") / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        self.assertEqual(tax, Decimal("234.57"))

    def test_margin_calculation(self):
        from decimal import Decimal, ROUND_HALF_UP
        cost = Decimal("1000.00")
        margin = Decimal("15")
        billed = (cost * (Decimal("100") + margin) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        self.assertEqual(billed, Decimal("1150.00"))

    def test_many_small_values(self):
        from decimal import Decimal
        values = [Decimal("0.01")] * 100
        self.assertEqual(sum(values), Decimal("1.00"))
