from abstract import ViURTestCase


class TestRandomSliceBoneInit(ViURTestCase):

    def test_default_init(self):
        from viur.core.bones import RandomSliceBone
        bone = RandomSliceBone()
        self.assertFalse(bone.visible)
        self.assertTrue(bone.readOnly)

    def test_visible_raises_not_implemented_error(self):
        from viur.core.bones import RandomSliceBone
        with self.assertRaises(NotImplementedError):
            RandomSliceBone(visible=True)

    def test_writable_raises_not_implemented_error(self):
        from viur.core.bones import RandomSliceBone
        with self.assertRaises(NotImplementedError):
            RandomSliceBone(readOnly=False)


class TestRandomSliceBoneSortSignature(ViURTestCase):
    """buildDBSort must accept the postfix argument of the base class."""

    def test_accepts_postfix_keyword(self):
        import inspect
        from viur.core.bones import RandomSliceBone
        params = inspect.signature(RandomSliceBone.buildDBSort).parameters
        self.assertIn("postfix", params)

    def test_signature_matches_base_bone(self):
        import inspect
        from viur.core.bones import RandomSliceBone
        from viur.core.bones.base import BaseBone
        self.assertEqual(
            list(inspect.signature(BaseBone.buildDBSort).parameters),
            list(inspect.signature(RandomSliceBone.buildDBSort).parameters),
        )
