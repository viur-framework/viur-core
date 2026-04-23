from abstract import ViURTestCase


class TestRawBoneSingleValueFromClient(ViURTestCase):
    """RawBone passes values through without modification."""

    def setUp(self):
        super().setUp()
        from viur.core.bones.raw import RawBone
        self.bone = RawBone()

    def _from_client(self, value):
        return self.bone.singleValueFromClient(value, {}, "data", {})

    def test_string_passthrough(self):
        val, err = self._from_client("hello")
        self.assertIsNone(err)
        self.assertEqual("hello", val)

    def test_dict_passthrough(self):
        val, err = self._from_client({"key": "value"})
        self.assertIsNone(err)
        self.assertEqual({"key": "value"}, val)

    def test_none_passthrough(self):
        val, err = self._from_client(None)
        self.assertIsNone(err)
        self.assertIsNone(val)

    def test_html_not_escaped(self):
        # RawBone does NOT escape HTML — that's the point
        val, err = self._from_client("<script>alert(1)</script>")
        self.assertIsNone(err)
        self.assertEqual("<script>alert(1)</script>", val)

    def test_type_suffix_in_type(self):
        from viur.core.bones.raw import RawBone
        bone = RawBone(type_suffix="code.python")
        self.assertEqual("raw.code.python", bone.type)
