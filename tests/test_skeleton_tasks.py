from unittest import mock

from abstract import ViURTestCase


class FakeKey:
    """A minimal stand-in for a db.Key, hashable and comparable by name."""

    def __init__(self, name: str):
        self.name = name

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other) -> bool:
        return isinstance(other, FakeKey) and other.name == self.name

    def __repr__(self) -> str:
        return f"<FakeKey {self.name}>"


class TestUpdateRelations(ViURTestCase):

    def _refreshed_keys(self, src_keys: list) -> list:
        """Run update_relations over relations with the given source keys.

        :param src_keys: One source key per ``viur-relations`` entry the query yields.
        :return: The keys actually passed to ``skel.patch()``.
        """
        from viur.core.skeleton import tasks

        relations = []
        for index, src_key in enumerate(src_keys):
            relation = dict(src=mock.Mock(key=src_key), viur_src_kind="wishlist")
            relation = type("Rel", (dict,), {})(relation)
            relation.key = f"relation-{index}"
            relations.append(relation)

        query = mock.MagicMock()
        query.run.return_value = relations
        query.getCursor.return_value = None
        query.filter.return_value = query

        refreshed = []
        skel = mock.MagicMock()
        skel.patch.side_effect = lambda *args, **kwargs: refreshed.append(kwargs.get("key"))

        with mock.patch.object(tasks.db, "Query", return_value=query), \
                mock.patch.object(tasks, "skeletonByKind", return_value=lambda: skel), \
                mock.patch.object(tasks.current, "request_data", mock.MagicMock()):
            tasks.update_relations(
                FakeKey("variant"),
                changed_bones=["shop_name"],
                _call_deferred=False,
            )
        return refreshed

    def test_same_source_is_refreshed_once(self):
        """A source referencing the destination N times must be refreshed only once.

        Without deduplication this stacks N transactions on the very same entity,
        which can exceed the request deadline and make the task retry forever.
        """
        source = FakeKey("wishlist-1")
        self.assertEqual(self._refreshed_keys([source] * 48), [source])

    def test_distinct_sources_are_all_refreshed(self):
        sources = [FakeKey(f"wishlist-{i}") for i in range(5)]
        self.assertEqual(self._refreshed_keys(sources), sources)

    def test_mixed_sources(self):
        first, second = FakeKey("wishlist-1"), FakeKey("wishlist-2")
        self.assertEqual(self._refreshed_keys([first, first, first, second]), [first, second])

    def test_no_relations(self):
        self.assertEqual(self._refreshed_keys([]), [])
