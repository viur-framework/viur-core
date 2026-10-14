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

        delete.assert_called_once_with(corrupt.key)
        put.assert_not_called()
