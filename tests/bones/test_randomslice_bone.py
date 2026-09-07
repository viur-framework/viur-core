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
