from abstract import ViURTestCase


class TestPhoneBoneIsInvalid(ViURTestCase):
    """PhoneBone.isInvalid: regex-based phone number validation."""

    def setUp(self):
        super().setUp()
        from viur.core.bones.phone import PhoneBone
        self.bone = PhoneBone()

    def _valid(self, value):
        self.assertIsNone(self.bone.isInvalid(value), msg=f"{value!r} should be valid")

    def _invalid(self, value):
        self.assertIsNotNone(self.bone.isInvalid(value), msg=f"{value!r} should be invalid")

    def test_empty_string(self):
        self._invalid("")

    def test_none(self):
        self._invalid(None)

    def test_international_format(self):
        self._valid("+49 151 12345678")

    def test_with_hyphens(self):
        self._valid("+1-800-555-1234")

    def test_local_format(self):
        self._valid("0151 12345678")

    def test_letters_invalid(self):
        self._invalid("abc-def-ghij")

    def test_too_many_digits(self):
        # max_length is 15 digits; 16 digits should exceed it
        self._invalid("+1234567890123456")


class TestPhoneBoneInit(ViURTestCase):
    def test_invalid_country_code_format(self):
        from viur.core.bones.phone import PhoneBone
        with self.assertRaises(ValueError):
            PhoneBone(default_country_code="0049")  # must start with +

    def test_valid_country_code(self):
        from viur.core.bones.phone import PhoneBone
        bone = PhoneBone(default_country_code="+49")
        self.assertEqual("+49", bone.default_country_code)

    def test_no_country_code(self):
        from viur.core.bones.phone import PhoneBone
        bone = PhoneBone()
        self.assertIsNone(bone.default_country_code)

    def test_custom_regex(self):
        from viur.core.bones.phone import PhoneBone
        bone = PhoneBone(test=r"^\d{5}$")
        self.assertIsNone(bone.isInvalid("12345"))
        self.assertIsNotNone(bone.isInvalid("+49 151 12345678"))

    def test_no_regex(self):
        from viur.core.bones.phone import PhoneBone
        # test=None disables regex check
        bone = PhoneBone(test=None)
        self.assertIsNone(bone.isInvalid("anything goes 123"))


class TestPhoneBoneSingleValueFromClient(ViURTestCase):
    """singleValueFromClient: normalization and country-code injection."""

    def _from_client(self, bone, value):
        return bone.singleValueFromClient(value, {}, "phone", {})

    def test_strips_whitespace(self):
        from viur.core.bones.phone import PhoneBone
        bone = PhoneBone()
        val, err = self._from_client(bone, "  +49 151 12345678  ")
        self.assertIsNone(err)
        self.assertEqual("+49 151 12345678", val)

    def test_00_prefix_converted_to_plus(self):
        from viur.core.bones.phone import PhoneBone
        bone = PhoneBone()
        val, err = self._from_client(bone, "0049 151 12345678")
        self.assertIsNone(err)
        self.assertEqual("+49 151 12345678", val)

    def test_default_country_code_prepended(self):
        from viur.core.bones.phone import PhoneBone
        bone = PhoneBone(default_country_code="+49")
        val, err = self._from_client(bone, "151 12345678")
        self.assertIsNone(err)
        self.assertEqual("+49 151 12345678", val)

    def test_leading_zero_stripped_with_country_code(self):
        from viur.core.bones.phone import PhoneBone
        bone = PhoneBone(default_country_code="+49")
        val, err = self._from_client(bone, "0151 12345678")
        self.assertIsNone(err)
        self.assertIn("+49", val)
        self.assertNotIn(" 0151", val)  # leading 0 on city code removed

    def test_invalid_returns_error(self):
        from viur.core.bones.phone import PhoneBone
        bone = PhoneBone()
        val, err = self._from_client(bone, "not-a-number")
        self.assertIsNotNone(err)
        self.assertEqual(bone.getEmptyValue(), val)
