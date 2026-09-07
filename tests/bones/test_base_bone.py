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


class TestReadFromClientException(ViURTestCase):
    """A single ReadFromClientError has to be accepted, as documented."""

    @staticmethod
    def _error():
        from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
        return ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "broken")

    def test_single_error(self):
        from viur.core.bones.base import ReadFromClientException
        error = self._error()
        exception = ReadFromClientException(error)
        self.assertEqual((error,), exception.errors)

    def test_iterable_of_errors(self):
        from viur.core.bones.base import ReadFromClientException
        errors = (self._error(), self._error())
        self.assertEqual(errors, ReadFromClientException(errors).errors)

    def test_empty_iterable_raises(self):
        from viur.core.bones.base import ReadFromClientException
        with self.assertRaises(ValueError):
            ReadFromClientException([])
