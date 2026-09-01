from unittest import mock

from abstract import ViURTestCase


class FakeKey:
    """A minimal stand-in for a db.Key, hashable and comparable by name."""

    def __init__(self, name: str, kind: str = "wishlist"):
        self.name = name
        self.kind = kind

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other) -> bool:
        return isinstance(other, FakeKey) and other.name == self.name

    def __repr__(self) -> str:
        return f"<FakeKey {self.name}>"


class TestPostDeletedHandler(ViURTestCase):

    def _deleted_keys(self, relation_count: int) -> tuple[list, mock.MagicMock]:
        """Run postDeletedHandler over a bone holding the given number of relations.

        :param relation_count: How many ``viur-relations`` entries the query yields.
        :return: The keys handed to ``db.delete``, and the query mock for further checks.
        """
        from viur.core.bones import relational

        keys = [FakeKey(f"relation-{index}") for index in range(relation_count)]
        query = mock.MagicMock()
        query.filter.return_value = query
        query.iter.return_value = iter(keys)

        deleted = []
        bone = relational.RelationalBone(kind="country")

        with mock.patch.object(relational.db, "Query", return_value=query), \
                mock.patch.object(relational.db, "delete", side_effect=deleted.extend) as delete:
            bone.postDeletedHandler(mock.MagicMock(), "testrelation", FakeKey("wishlist-1"))

        delete.assert_called_once()
        return deleted, query

    def test_every_relation_is_deleted(self) -> None:
        """More relations than conf.db.query_default_limit must all be removed.

        query.run() stops at that limit and would leave the rest behind as orphans
        with a src key pointing at an entity that no longer exists.
        """
        deleted, query = self._deleted_keys(250)
        self.assertEqual(len(deleted), 250)
        query.run.assert_not_called()

    def test_only_keys_are_fetched(self) -> None:
        _, query = self._deleted_keys(5)
        query.iter.assert_called_once_with(keys_only=True)

    def test_a_bone_without_relations_deletes_nothing(self) -> None:
        deleted, _ = self._deleted_keys(0)
        self.assertEqual(deleted, [])
