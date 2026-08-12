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

    def test_getDefaultValue_multiple_no_shared_list(self):
        from viur.core.bones import BaseBone
        bone = BaseBone(multiple=True)

        value = bone.getDefaultValue(None)
        self.assertEqual([], value)

        value.append("foo")
        self.assertEqual([], bone.getDefaultValue(None))
