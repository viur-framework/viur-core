from unittest import mock

from abstract import ViURTestCase


class TestRelationalBonePostSavedHandler(ViURTestCase):

    def test_relation_with_empty_dest_is_deleted(self):
        """A ``viur-relations`` entry stored with ``dest=None`` is corrupt and must be removed.

        Before, only a missing ``dest`` (``KeyError``) was handled; an empty one raised
        ``AttributeError`` and aborted the write of the source skeleton.
        """
        from viur.core import db
        from viur.core.bones import RelationalBone
        from viur.core.bones import relational

        bone = RelationalBone(kind="dest_kind")
        key = db.Key("src_kind", 1)
        skel = mock.MagicMock()
        skel.__getitem__.return_value = None  # the relation has no value
        skel.dbEntity = None

        corrupt = db.Entity()
        corrupt["dest"] = None
        corrupt.key = db.Key("viur-relations", 2, parent=key)

        query = mock.MagicMock()
        query.filter.return_value = query
        query.iter.return_value = [corrupt]

        with mock.patch.object(relational.db, "Query", return_value=query), \
                mock.patch.object(relational.db, "delete") as delete, \
                mock.patch.object(relational.db, "put") as put:
            bone.postSavedHandler(skel, "relation", key)

        delete.assert_called_once_with([corrupt.key])
        put.assert_not_called()


class TestRelationalBoneShortkeys(ViURTestCase):
    """A shortkey is the ``id_or_name`` of a key, passed instead of the full key."""

    def _bone(self, **kwargs):
        from viur.core.bones import RelationalBone

        bone = RelationalBone(kind="dest_kind", **kwargs)
        bone._ref_keys = {"key", "name"}
        return bone

    def _filter(self, bone, value):
        from viur.core import db
        from viur.core.bones import KeyBone

        query = mock.MagicMock()
        query.queries = db.QueryDefinition("dest_kind", {}, [])
        with mock.patch.object(bone, "_getSkels", return_value=({"key": KeyBone()}, None)):
            bone.buildDBFilter("rel", mock.MagicMock(), query, {"rel.dest.key": value})
        return query

    def test_filter_by_int_shortkey(self):
        """A numeric string from a query is an integer id."""
        from viur.core import db

        query = self._filter(self._bone(), "123")
        query.filter.assert_called_once_with("rel.dest.__key__ =", db.Key("dest_kind", 123))

    def test_filter_by_name_shortkey(self):
        from viur.core import db

        query = self._filter(self._bone(), "abc")
        query.filter.assert_called_once_with("rel.dest.__key__ =", db.Key("dest_kind", "abc"))

    def test_filter_by_full_key(self):
        from viur.core import db

        key = db.Key("dest_kind", 123)
        query = self._filter(self._bone(), key.to_legacy_urlsafe().decode())
        query.filter.assert_called_once_with("rel.dest.__key__ =", key)

    def test_filter_by_shortkey_list(self):
        from viur.core import db

        query = self._filter(self._bone(), ["1", "abc"])
        keys = [q.filters["rel.dest.__key__ ="] for q in query.queries]
        self.assertEqual(keys, [db.Key("dest_kind", 1), db.Key("dest_kind", "abc")])

    def test_from_client_keeps_deleted_relation_by_shortkey(self):
        """With ``Ignore`` consistency a stale relation is kept, also if the client sends only the shortkey."""
        from viur.core import db
        from viur.core.bones.relational import RelationalConsistency

        bone = self._bone(consistency=RelationalConsistency.Ignore)
        stale = {"dest": {"key": db.Key("dest_kind", 123)}, "rel": None}

        with mock.patch.object(bone, "createRelSkelFromKey", return_value=None), \
                mock.patch.object(bone, "iter_bone_value", return_value=[(None, None, stale)]):
            value, errors = bone.singleValueFromClient("123", mock.MagicMock(), "rel", {})

        self.assertIs(value, stale)
        self.assertEqual(errors, [])
