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

    def test_rgb_short_3_chars_expanded(self):
        # "abc" → prepend # → "#abc" (len 4) → CSS shorthand expansion:
        # value[0:2] + value[1] + 2*value[2] + 2*value[3] = "#a"+"a"+"bb"+"cc" = "#aabbcc"
        self._valid(self.rgb, "abc", "#aabbcc")

    def test_rgb_hash_short_3_chars_expanded(self):
        # "#abc" (len 4) → same CSS shorthand expansion → "#aabbcc"
        self._valid(self.rgb, "#abc", "#aabbcc")

    def test_rgb_uppercase_normalised(self):
        self._valid(self.rgb, "AABBCC", "#aabbcc")

    def test_rgb_invalid_char(self):
        self._invalid(self.rgb, "#gghhii")

    def test_rgb_double_hash(self):
        self._invalid(self.rgb, "##aabbcc")

    def test_rgb_wrong_length(self):
        # 8-char hex is RGBA length, not valid in rgb mode
        self._invalid(self.rgb, "aabbccdd")

    # --- RGBA mode ---

    def test_rgba_full_with_hash(self):
        self._valid(self.rgba, "#aabbccdd", "#aabbccdd")

    def test_rgba_full_without_hash(self):
        self._valid(self.rgba, "aabbccdd", "#aabbccdd")

    def test_rgba_invalid_length(self):
        self._invalid(self.rgba, "#aabbcc")  # RGB length, not RGBA

    def test_rgba_invalid_char(self):
        self._invalid(self.rgba, "#aabbccgg")

    # --- mode validation ---

    def test_invalid_mode_raises(self):
        from viur.core.bones.color import ColorBone
        with self.assertRaises(AssertionError):
            ColorBone(mode="hsv")
