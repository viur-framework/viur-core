from abstract import ViURTestCase


class TestUidBoneInit(ViURTestCase):

    def _make(self, **kwargs):
        from viur.core.bones.uid import UidBone
        return UidBone(readOnly=True, **kwargs)

    def test_default_init(self):
        bone = self._make()
        self.assertEqual("*", bone.fillchar)
        self.assertEqual(13, bone.length)
        self.assertEqual("*", bone.pattern)

    def test_custom_pattern(self):
        bone = self._make(pattern="ORD-*")
        self.assertEqual("ORD-*", bone.pattern)

    def test_custom_fillchar(self):
        bone = self._make(fillchar="0")
        self.assertEqual("0", bone.fillchar)

    def test_custom_length(self):
        bone = self._make(length=8)
        self.assertEqual(8, bone.length)

    def test_multiple_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=True, multiple=True)

    def test_not_readonly_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=False)

    def test_pattern_without_wildcard_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=True, pattern="NO-WILDCARD")

    def test_pattern_with_two_wildcards_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=True, pattern="**")

    def test_fillchar_multiple_chars_raises(self):
        from viur.core.bones.uid import UidBone
        with self.assertRaises(ValueError):
            UidBone(readOnly=True, fillchar="00")

    def test_callable_pattern(self):
        bone = self._make(pattern=lambda: "INV-*")
        self.assertEqual("INV-*", bone.pattern)


class TestUidBoneStructure(ViURTestCase):

    def test_structure_keys(self):
        from viur.core.bones.uid import UidBone
        bone = UidBone(readOnly=True, pattern="INV-*", length=10, fillchar="0")
        s = bone.structure()
        self.assertEqual("INV-*", s["pattern"])
        self.assertEqual(10, s["length"])
        self.assertEqual("0", s["fillchar"])
