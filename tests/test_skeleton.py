"""Tests for :class:`viur.core.skeleton.SkeletonInstance` and :meth:`Skeleton.write`."""
from unittest import mock

from abstract import ViURTestCase


def _skeleton_search_path():
    """Make ``TranslationSkel`` importable, see :mod:`tests.modules.test_user_app_login`."""
    from viur.core.config import conf
    if "/src/viur/core/" not in conf.skeleton_search_path:
        conf.skeleton_search_path = list(conf.skeleton_search_path) + ["/src/viur/core/"]


def _translation_skel():
    from viur.core import bones, db  # noqa: F401  (import order, see project memory)
    _skeleton_search_path()
    from viur.core.modules.translation import TranslationSkel
    return TranslationSkel


class TestBoneMapModification(ViURTestCase):
    """``skel.bone = None`` removes a bone from the SkeletonInstance."""

    def test_assigning_none_removes_the_bone(self):
        skel = _translation_skel()()
        skel.hint = None
        self.assertNotIn("hint", skel)
        self.assertIn("default_text", skel)

    def test_reassigning_the_bone_takes_it_back(self):
        from viur.core.bones import StringBone
        skel = _translation_skel()()
        skel.hint = None
        skel.hint = StringBone(descr="hint")
        self.assertIn("hint", skel)

    def test_removal_survives_cloning(self):
        skel = _translation_skel()()
        skel.hint = None
        self.assertNotIn("hint", skel.clone())


class TestWriteRespectsBoneMap(ViURTestCase):
    """A bone removed from the skeleton must not be serialized by ``write()``."""

    def _write(self, skel, stored=None):
        """Run ``skel.write()`` against a mocked datastore.

        :param stored: The ``db.Entity`` the datastore already holds for the skeleton, if any.
        :return: The ``db.Entity`` that was written for the skeleton itself.
        """
        from viur.core import db
        from viur.core.skeleton import tasks

        written = []
        key = db.Key(skel.kindName, "test-entry")

        def get(db_key):
            """Only answer for the entity itself; unique- and blob-locks stay unclaimed."""
            if db_key.kind == skel.kindName:
                return stored
            return None

        with mock.patch.object(db, "allocate_ids", return_value=[key]), \
                mock.patch.object(db, "get", side_effect=get), \
                mock.patch.object(db, "put", side_effect=written.append), \
                mock.patch.object(db, "is_in_transaction", return_value=True), \
                mock.patch.object(tasks, "update_relations", mock.Mock()):
            skel.write()

        entities = [entity for entity in written if entity.key.kind == skel.kindName]
        self.assertEqual(1, len(entities))
        return entities[0]

    def test_removed_bone_is_not_written(self):
        skel = _translation_skel()()
        skel["name"] = "some.key"
        skel.hint = None
        entity = self._write(skel)
        self.assertNotIn("hint", entity)
        self.assertIn("default_text", entity)

    def test_removing_a_bone_keeps_the_values_of_the_others(self):
        skel = _translation_skel()()
        skel["name"] = "some.key"
        skel["default_text"] = "kept"
        skel.hint = None
        self.assertEqual("kept", self._write(skel)["default_text"])

    def test_removed_bone_keeps_the_value_already_stored(self):
        """Removing a bone excludes it from the write -- it does not clear the stored value."""
        from viur.core import db
        skel_cls = _translation_skel()
        stored = db.Entity(db.Key(skel_cls.kindName, "test-entry"))
        stored["name"] = "some.key"
        stored["hint"] = "kept"

        skel = skel_cls()
        skel.setEntity(stored)
        skel.hint = None
        entity = self._write(skel, stored=stored)
        self.assertEqual("kept", entity["hint"])

    def test_exactly_the_removed_bone_is_missing(self):
        """The bone map take-over must not drop anything but the bone that was removed."""
        skel_cls = _translation_skel()

        full = skel_cls()
        full["name"] = "some.key"

        reduced = skel_cls()
        reduced["name"] = "some.key"
        reduced.hint = None

        self.assertEqual(
            set(self._write(full).keys()) - {"hint"},
            set(self._write(reduced).keys()),
        )

    def test_removed_bone_keeps_its_blobs_locked(self):
        """Excluding a bone from the write must not release its blobs for deletion.

        The blob-lock is rebuilt from ``blob_list`` on every write: whatever is missing from
        it lands in ``old_blob_references``, and ``doCheckForUnreferencedBlobs`` marks those
        files for deletion -- while the entity still references them.
        """
        from viur.core import db
        from viur.core.bones import StringBone
        from viur.core.skeleton import tasks
        skel_cls = _translation_skel()

        stored = db.Entity(db.Key(skel_cls.kindName, "test-entry"))
        stored["name"] = "some.key"
        stored["hint"] = "references-a-blob"

        lock = db.Entity(db.Key("viur-blob-locks", "test-entry"))
        lock["active_blob_references"] = ["blob-1"]
        lock["old_blob_references"] = []
        lock["has_old_blob_references"] = False
        lock["is_stale"] = False

        def get(db_key):
            return {skel_cls.kindName: stored, "viur-blob-locks": lock}.get(db_key.kind)

        def referenced_blobs(self, skel, bone_name):
            return {"blob-1"} if bone_name == "hint" else set()

        skel = skel_cls()
        skel.setEntity(stored)
        skel["key"] = stored.key
        skel.hint = None

        with mock.patch.object(db, "get", side_effect=get), \
                mock.patch.object(db, "put", mock.Mock()), \
                mock.patch.object(db, "is_in_transaction", return_value=True), \
                mock.patch.object(StringBone, "getReferencedBlobs", referenced_blobs), \
                mock.patch.object(tasks, "update_relations", mock.Mock()):
            skel.write()

        self.assertEqual(["blob-1"], lock["active_blob_references"])
        self.assertEqual([], lock["old_blob_references"])

    def test_removed_bone_stays_in_the_search_index(self):
        """``ViurTagsSearchAdapter.prewrite`` replaces viurTags from the bones it sees.

        A bone excluded from the write keeps its stored value, so its search tags have to
        survive too -- otherwise editing through a skeleton that hides the bone makes the
        stored value unfindable.
        """
        from viur.core import db
        skel_cls = _translation_skel()

        stored = db.Entity(db.Key(skel_cls.kindName, "test-entry"))
        stored["name"] = "some.key"
        stored["translations"] = {"_viurLanguageWrapper_": True, "en": "searchable text"}

        skel = skel_cls()
        skel.setEntity(stored)
        skel["key"] = stored.key
        skel.translations = None
        self._write(skel, stored=stored)

        self.assertIn("searchable", stored["viurTags"])
