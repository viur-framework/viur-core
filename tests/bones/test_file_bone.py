from abstract import ViURTestCase


class TestFileBoneRefKeys(ViURTestCase):
    """FileBone.__init__: refKeys required by isInvalid must be present."""

    # --- accepted configurations ---

    def test_defaults_are_operable(self):
        from viur.core.bones import FileBone
        bone = FileBone()
        self.assertIn("public", bone.refKeys)

    def test_minimal_refkeys_without_validation(self):
        from viur.core.bones import FileBone
        bone = FileBone(refKeys=["dlkey", "name", "public"])
        self.assertEqual({"dlkey", "name", "public"}, bone.refKeys & {"dlkey", "name", "public"})

    def test_mimetype_not_required_without_valid_mime_types(self):
        from viur.core.bones import FileBone
        FileBone(refKeys=["dlkey", "name", "public", "size"])

    def test_size_not_required_without_max_file_size(self):
        from viur.core.bones import FileBone
        FileBone(refKeys=["dlkey", "name", "public", "mimetype"])

    # --- rejected configurations ---

    def test_missing_dlkey_raises(self):
        from viur.core.bones import FileBone
        with self.assertRaises(ValueError):
            FileBone(refKeys=["name", "public"])

    def test_missing_name_raises(self):
        from viur.core.bones import FileBone
        with self.assertRaises(ValueError):
            FileBone(refKeys=["dlkey", "public"])

    def test_missing_public_raises(self):
        from viur.core.bones import FileBone
        with self.assertRaises(ValueError) as cm:
            FileBone(refKeys=["dlkey", "name"])
        self.assertIn("public", str(cm.exception))

    def test_missing_mimetype_with_valid_mime_types_raises(self):
        from viur.core.bones import FileBone
        with self.assertRaises(ValueError) as cm:
            FileBone(
                refKeys=["dlkey", "name", "public"],
                validMimeTypes=["image/*"],
            )
        self.assertIn("mimetype", str(cm.exception))

    def test_missing_size_with_max_file_size_raises(self):
        from viur.core.bones import FileBone
        with self.assertRaises(ValueError) as cm:
            FileBone(
                refKeys=["dlkey", "name", "public"],
                maxFileSize=1024,
            )
        self.assertIn("size", str(cm.exception))


class TestFileBoneDefaultRefKeys(ViURTestCase):
    """FileBone.DEFAULT_REFKEYS is documented as an extendable reference."""

    def test_extended_class_attribute_is_honored(self):
        from viur.core.bones import FileBone
        original = FileBone.DEFAULT_REFKEYS
        FileBone.DEFAULT_REFKEYS = ("foo",) + original
        try:
            bone = FileBone()
            self.assertIn("foo", bone.refKeys)
        finally:
            FileBone.DEFAULT_REFKEYS = original

    def test_extended_class_attribute_is_honored_by_image_bone(self):
        from viur.core.bones import FileBone, ImageBone
        original = FileBone.DEFAULT_REFKEYS
        FileBone.DEFAULT_REFKEYS = ("foo",) + original
        try:
            bone = ImageBone()
            self.assertIn("foo", bone.refKeys)
        finally:
            FileBone.DEFAULT_REFKEYS = original

    def test_subclass_may_override_default_refkeys(self):
        from viur.core.bones import FileBone

        class MyFileBone(FileBone):
            DEFAULT_REFKEYS = ("foo",) + FileBone.DEFAULT_REFKEYS

        bone = MyFileBone()
        self.assertIn("foo", bone.refKeys)

    def test_explicit_refkeys_still_win(self):
        from viur.core.bones import FileBone
        bone = FileBone(refKeys=["dlkey", "name", "public"])
        self.assertNotIn("size", bone.refKeys)
