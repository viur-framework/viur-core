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
