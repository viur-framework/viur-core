from unittest import mock

from abstract import ViURTestCase


class TestKeyBone_serialize(ViURTestCase):
    """A KeyBone must always store a ``db.Key``, even when a urlsafe string was assigned.

    ``History.write_to_viur`` assigns ``current_key`` as a urlsafe string. Stored as-is, the
    ``current_key`` filter (which decodes to a ``db.Key``) never matched any entry.
    """

    bone_name = "current_key"

    def _serialize(self, bone, value):
        from viur.core import db

        skel = mock.MagicMock()
        skel.accessedValues = {self.bone_name: value}
        skel.dbEntity = db.Entity()
        self.assertTrue(bone.serialize(skel, self.bone_name, True))
        return skel.dbEntity[self.bone_name]

    def _filter_value(self, bone, raw_value):
        from viur.core import db

        query = db.Query("history")
        bone.buildDBFilter(self.bone_name, mock.MagicMock(), query, {self.bone_name: raw_value})
        return query.queries.filters[f"{self.bone_name} ="]

    def test_key_is_stored_unchanged(self):
        from viur.core import db
        from viur.core.bones import KeyBone

        key = db.Key("history_kind", "abc")
        stored = self._serialize(KeyBone(), key)
        self.assertIsInstance(stored, db.Key)
        self.assertEqual(key, stored)

    def test_urlsafe_string_is_stored_as_key(self):
        from viur.core import db
        from viur.core.bones import KeyBone

        key = db.Key("history_kind", "abc")
        stored = self._serialize(KeyBone(), key.to_legacy_urlsafe().decode())
        self.assertIsInstance(stored, db.Key)
        self.assertEqual(key, stored)

    def test_str_of_key_is_stored_as_key(self):
        """``create_history_entry`` passes ``str(skel["key"])``."""
        from viur.core import db
        from viur.core.bones import KeyBone

        key = db.Key("parent_kind", 1, parent=None)
        key = db.Key("history_kind", 42, parent=key)
        stored = self._serialize(KeyBone(), str(key))
        self.assertIsInstance(stored, db.Key)
        self.assertEqual(key, stored)

    def test_stored_value_matches_filter_value(self):
        """The value written by ``serialize`` must be equal to the one ``buildDBFilter`` queries for."""
        from viur.core import db
        from viur.core.bones import KeyBone

        bone = KeyBone()
        urlsafe = db.Key("history_kind", "abc").to_legacy_urlsafe().decode()
        self.assertEqual(self._filter_value(bone, urlsafe), self._serialize(bone, urlsafe))

    def test_empty_value_is_stored_as_none(self):
        """An unset KeyBone (default ``None``) must not break writing the skeleton."""
        from viur.core.bones import KeyBone

        self.assertIsNone(self._serialize(KeyBone(), None))

    def test_multiple_values_are_stored_as_keys(self):
        from viur.core import db
        from viur.core.bones import KeyBone

        keys = [db.Key("history_kind", "a"), db.Key("history_kind", "b")]
        stored = self._serialize(KeyBone(multiple=True), [keys[0], str(keys[1])])
        self.assertEqual(keys, stored)
        self.assertTrue(all(isinstance(key, db.Key) for key in stored))

    def test_invalid_string_raises(self):
        from viur.core.bones import KeyBone

        with self.assertRaises(Exception):
            self._serialize(KeyBone(), "not-a-key")

    def test_shortkey_with_allowed_kinds_is_stored_as_key(self):
        from viur.core import db
        from viur.core.bones import KeyBone

        bone = KeyBone(allowed_kinds=["history_kind"])
        self.assertEqual(db.Key("history_kind", "abc"), self._serialize(bone, "abc"))
        self.assertEqual(db.Key("history_kind", 42), self._serialize(bone, "42"))

    def test_shortkey_without_allowed_kinds_raises(self):
        """Without ``allowed_kinds`` there is no kind to build a key from a shortkey."""
        from viur.core.bones import KeyBone

        with self.assertRaises(ValueError):
            self._serialize(KeyBone(), "abc")

    def test_key_of_wrong_kind_raises(self):
        from viur.core import db
        from viur.core.bones import KeyBone

        with self.assertRaises(ValueError):
            self._serialize(KeyBone(allowed_kinds=["history_kind"]), db.Key("other_kind", "abc"))

    def test_empty_value_with_allowed_kinds_is_stored_as_none(self):
        """``key_helper(None)`` raises, so empty values must be handled before parsing."""
        from viur.core.bones import KeyBone

        self.assertIsNone(self._serialize(KeyBone(allowed_kinds=["history_kind"]), None))

    def test_foreign_project_key_is_normalized(self):
        from viur.core import conf, db
        from viur.core.bones import KeyBone

        foreign = db.Key("history_kind", "abc", project="s~" + conf.instance.project_id)
        stored = self._serialize(KeyBone(), foreign)
        self.assertEqual(conf.instance.project_id, stored.project)
