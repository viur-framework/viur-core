from unittest import mock

from abstract import ViURTestCase
from viur.core import conf
from viur.core.bones.file import FileBone
from viur.core.skeleton import Skeleton

# MetaSkel only accepts skeletons defined below conf.skeleton_search_path. The paths
# are relative to the test root, so this file is seen as "/bones/test_file_bone.py".
conf.skeleton_search_path = tuple(conf.skeleton_search_path) + ("/bones/",)

# Importing the file module registers FileSkel as kind "file", which the FileBone
# needs to build its RefSkel. The module creates a GCS client on import.
with mock.patch("google.cloud.storage.Client"):
    from viur.core.modules.file import File  # noqa: F401


class StructureProbeSkel(Skeleton):
    """Host skeleton, so the bone below gets a RefSkel to report its structure from."""
    kindName = "structure_probe"
    file = FileBone(maxFileSize=1024, validMimeTypes=["image/*"])


class TestFileBoneStructure(ViURTestCase):
    """FileBone.structure: values the admin UI needs before uploading."""

    def setUp(self):
        super().setUp()
        self.bone = StructureProbeSkel.file
        self.bone.setSystemInitialized()

    def test_max_file_size_is_exported(self):
        self.assertEqual(1024, self.bone.structure()["max_file_size"])

    def test_valid_mime_types_are_exported(self):
        self.assertEqual(["image/*"], self.bone.structure()["valid_mime_types"])

    def test_public_is_exported(self):
        self.assertIs(False, self.bone.structure()["public"])


class TestFileBoneRefKeys(ViURTestCase):
    """FileBone.__init__: refKeys required by isInvalid must be present."""

    def setUp(self):
        super().setUp()
        from viur.core.bones.file import FileBone
        self.FileBone = FileBone

    # --- accepted configurations ---

    def test_defaults_are_operable(self):
        bone = self.FileBone()
        self.assertIn("public", bone.refKeys)

    def test_minimal_refkeys_without_validation(self):
        bone = self.FileBone(refKeys=["dlkey", "name", "public"])
        self.assertEqual({"dlkey", "name", "public"}, bone.refKeys & {"dlkey", "name", "public"})

    def test_mimetype_not_required_without_valid_mime_types(self):
        self.FileBone(refKeys=["dlkey", "name", "public", "size"])

    def test_size_not_required_without_max_file_size(self):
        self.FileBone(refKeys=["dlkey", "name", "public", "mimetype"])

    # --- rejected configurations ---

    def test_missing_dlkey_raises(self):
        with self.assertRaises(ValueError):
            self.FileBone(refKeys=["name", "public"])

    def test_missing_name_raises(self):
        with self.assertRaises(ValueError):
            self.FileBone(refKeys=["dlkey", "public"])

    def test_missing_public_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.FileBone(refKeys=["dlkey", "name"])
        self.assertIn("public", str(cm.exception))

    def test_missing_mimetype_with_valid_mime_types_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.FileBone(
                refKeys=["dlkey", "name", "public"],
                validMimeTypes=["image/*"],
            )
        self.assertIn("mimetype", str(cm.exception))

    def test_missing_size_with_max_file_size_raises(self):
        with self.assertRaises(ValueError) as cm:
            self.FileBone(
                refKeys=["dlkey", "name", "public"],
                maxFileSize=1024,
            )
        self.assertIn("size", str(cm.exception))
