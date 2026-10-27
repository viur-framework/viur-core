from abstract import ViURTestCase


class TestBaseBone_getDefaultValue(ViURTestCase):
    def test_getDefaultValue_languages_multiple_no_shared_list(self):
        from viur.core.bones import BaseBone
        bone = BaseBone(languages=["de", "en"], multiple=True)

        value = bone.getDefaultValue(None)
        self.assertEqual({"de": [], "en": []}, value)
        # Each language must get its own list instance
        self.assertIsNot(value["de"], value["en"])

        # Mutating one language must not affect the others
        value["de"].append("foo")
        self.assertEqual([], value["en"])

        # ... and must not pollute the default of the next skeleton
        self.assertEqual({"de": [], "en": []}, bone.getDefaultValue(None))

    def test_getDefaultValue_languages_default_key_no_shared_list(self):
        from viur.core.bones import BaseBone
        bone = BaseBone(languages=["de", "en"], multiple=True, defaultValue={"__default__": ["x"]})

        value = bone.getDefaultValue(None)
        self.assertEqual({"de": ["x"], "en": ["x"]}, value)
        self.assertIsNot(value["de"], value["en"])

        value["de"].append("y")
        self.assertEqual(["x"], value["en"])
        self.assertEqual({"de": ["x"], "en": ["x"]}, bone.getDefaultValue(None))

    def test_getDefaultValue_multiple_no_shared_list(self):
        from viur.core.bones import BaseBone
        bone = BaseBone(multiple=True)

        value = bone.getDefaultValue(None)
        self.assertEqual([], value)

        value.append("foo")
        self.assertEqual([], bone.getDefaultValue(None))


class TestBaseBone_iter_bone_value(ViURTestCase):
    def _iter(self, bone, value):
        return list(bone.iter_bone_value({"bone": value}, "bone"))

    def test_single(self):
        from viur.core.bones import BaseBone
        self.assertEqual([(None, None, "a")], self._iter(BaseBone(), "a"))

    def test_multiple(self):
        from viur.core.bones import BaseBone
        self.assertEqual([(0, None, "a"), (1, None, "b")], self._iter(BaseBone(multiple=True), ["a", "b"]))

    def test_languages(self):
        from viur.core.bones import BaseBone
        bone = BaseBone(languages=["de", "en"])
        self.assertEqual([(None, "de", "a"), (None, "en", "b")], self._iter(bone, {"de": "a", "en": "b"}))

    def test_languages_multiple_index_per_language(self):
        """The index is the position of the value within its language, not the position of the language."""
        from viur.core.bones import BaseBone
        bone = BaseBone(languages=["de", "en"], multiple=True)
        self.assertEqual(
            [(0, "de", "a"), (1, "de", "b"), (0, "en", "c"), (1, "en", "d"), (2, "en", "e")],
            self._iter(bone, {"de": ["a", "b"], "en": ["c", "d", "e"]}),
        )

    def test_languages_multiple_skips_empty_language(self):
        from viur.core.bones import BaseBone
        bone = BaseBone(languages=["de", "en"], multiple=True)
        self.assertEqual([(0, "en", "c")], self._iter(bone, {"de": [], "en": ["c"]}))
