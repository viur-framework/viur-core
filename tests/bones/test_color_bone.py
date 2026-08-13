from abstract import ViURTestCase


class TestColorBoneSingleValueFromClient(ViURTestCase):
    """ColorBone.singleValueFromClient: hex color normalization and validation."""

    def _from_client(self, bone, value):
        return bone.singleValueFromClient(value, {}, "color", {})

    def _valid(self, bone, value, expected=None):
        val, err = self._from_client(bone, value)
        self.assertIsNone(err, msg=f"{value!r} should be valid, got err={err}")
        if expected is not None:
            self.assertEqual(expected, val)

    def _invalid(self, bone, value):
        val, err = self._from_client(bone, value)
        self.assertIsNotNone(err, msg=f"{value!r} should be invalid")

    # --- RGB mode (default) ---

    def setUp(self):
        super().setUp()
        from viur.core.bones.color import ColorBone
        self.rgb = ColorBone(mode="rgb")
        self.rgba = ColorBone(mode="rgba")

    def test_rgb_full_with_hash(self):
        self._valid(self.rgb, "#aabbcc", "#aabbcc")

    def test_rgb_full_without_hash(self):
        self._valid(self.rgb, "aabbcc", "#aabbcc")

    def test_rgb_short_3_chars(self):
        # 3 chars → prepend # → expand is handled differently
        # "abc" → "#abc" → length 4 → expansion: #a + a + bb + cc
        val, err = self._from_client(self.rgb, "abc")
        self.assertIsNone(err)

    def test_rgb_uppercase_normalised(self):
        self._valid(self.rgb, "AABBCC", "#aabbcc")

    def test_rgb_invalid_char(self):
        self._invalid(self.rgb, "#gghhii")

    def test_rgb_double_hash(self):
        self._invalid(self.rgb, "##aabbcc")

    def test_rgb_wrong_length(self):
        # 8-char hex is RGBA length, not valid in rgb mode
        self._invalid(self.rgb, "aabbccdd")

    def test_rgb_short_3_chars_expanded(self):
        self._valid(self.rgb, "abc", "#aabbcc")

    def test_rgb_short_3_chars_with_hash_expanded(self):
        self._valid(self.rgb, "#abc", "#aabbcc")

    def test_rgb_short_2_chars_with_hash(self):
        # "#ab" is 2 hex digits, no valid length
        self._invalid(self.rgb, "#ab")

    def test_rgb_seven_hex_digits_without_hash(self):
        self._invalid(self.rgb, "abcdefa")

    def test_rgb_hash_in_the_middle(self):
        self._invalid(self.rgb, "ab#cde")

    def test_rgb_hash_only(self):
        self._invalid(self.rgb, "#")

    def test_rgb_empty_string(self):
        self._invalid(self.rgb, "")

    def test_rgb_non_string_value(self):
        # a JSON client may send anything - must be a validation error, not a crash
        self._invalid(self.rgb, 123)

    def test_rgb_non_string_container(self):
        self._invalid(self.rgb, {"color": "#aabbcc"})

    # --- RGBA mode ---

    def test_rgba_full_with_hash(self):
        self._valid(self.rgba, "#aabbccdd", "#aabbccdd")

    def test_rgba_full_without_hash(self):
        self._valid(self.rgba, "aabbccdd", "#aabbccdd")

    def test_rgba_invalid_length(self):
        self._invalid(self.rgba, "#aabbcc")  # RGB length, not RGBA

    def test_rgba_invalid_char(self):
        self._invalid(self.rgba, "#aabbccgg")

    def test_rgba_short_3_chars(self):
        # the rgb shorthand is not expanded in rgba mode
        self._invalid(self.rgba, "abc")

    def test_rgba_hash_in_the_middle(self):
        self._invalid(self.rgba, "aabb#ccdd")

    def test_rgba_non_string_value(self):
        self._invalid(self.rgba, 123)

    # --- mode validation ---

    def test_invalid_mode_raises(self):
        from viur.core.bones.color import ColorBone
        with self.assertRaises(AssertionError):
            ColorBone(mode="hsv")


class TestColorBoneStructure(ViURTestCase):
    """ColorBone.structure: the mode must reach the client."""

    def test_structure_contains_rgb_mode(self):
        from viur.core.bones.color import ColorBone
        self.assertEqual("rgb", ColorBone().structure()["mode"])

    def test_structure_contains_rgba_mode(self):
        from viur.core.bones.color import ColorBone
        self.assertEqual("rgba", ColorBone(mode="rgba").structure()["mode"])
