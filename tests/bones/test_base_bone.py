from abstract import ViURTestCase


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
        with self.assertRaises(AttributeError):
            bone.readonly = True  # typo of readOnly -> must be rejected

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
