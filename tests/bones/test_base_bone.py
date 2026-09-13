import traceback

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


class TestBoneStrictMode(ViURTestCase):
    """conf.bone_strict_mode rejects assigning an *unknown* attribute to a bone after construction.

    Guards against the typo class ``bone.readonly = True`` (dead attribute) instead of the real
    ``bone.readOnly``, which silently disabled access controls in the wild.
    """

    def tearDown(self):
        from viur.core import conf
        conf.bone_strict_mode = True  # restore default so the flag does not leak into other tests
        super().tearDown()

    def _sealed_bone(self):
        """A bone that is 'construction complete' (sealed via __set_name__) and marked cloned, so
        only the strict-mode guard is in play (not the unrelated 'clone first' guard)."""
        from viur.core.bones import StringBone
        bone = StringBone()
        bone.__set_name__(TestBoneStrictMode, "test")  # binds to a skel -> seals the bone
        bone.isClonedInstance = True
        return bone

    def test_unknown_attr_raises_when_strict(self):
        from viur.core import conf
        conf.bone_strict_mode = True
        bone = self._sealed_bone()
        with self.assertRaises(AttributeError) as cm:
            bone.readonly = True  # typo of readOnly -> must be rejected
        # Python's traceback machinery derives the suggestion from AttributeError.name/.obj
        self.assertIn("Did you mean: 'readOnly'", "".join(traceback.format_exception_only(cm.exception)))

    def test_known_attr_allowed_when_strict(self):
        from viur.core import conf
        conf.bone_strict_mode = True
        bone = self._sealed_bone()
        bone.readOnly = True  # existing attribute -> allowed
        self.assertTrue(bone.readOnly)

    def test_unknown_attr_allowed_when_disabled(self):
        from viur.core import conf
        conf.bone_strict_mode = False
        bone = self._sealed_bone()
        bone.readonly = True  # guard off -> legacy silent-set behaviour
        self.assertTrue(bone.readonly)

    def test_construction_kwarg_typo_still_raises(self):
        # Pre-existing behaviour (no **kwargs on BaseBone.__init__): unknown ctor kwargs raise.
        from viur.core.bones import NumericBone
        with self.assertRaises(TypeError):
            NumericBone(reqired=True)
