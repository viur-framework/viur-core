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


class TestUpdateRelationsVisitsEachRelationOnce(ViURTestCase):
    """Refreshing a source rewrites its relations with ``viur_delayed_update_tag = now``. On the datastore a cursor
    is a position in the index, ordered by that tag, so the rewritten relations lie behind it; while the tag was still
    below ``min_change_time`` the next page found them again, and the chain refreshed the same sources until the
    cutoff passed."""

    NOW = 1_000_000.0
    PAGE = 2

    def test_each_source_is_refreshed_once_across_pages(self):
        from viur.core.skeleton import tasks

        def relation(i, src, tag):
            rel = type("Rel", (dict,), {})(
                src=mock.Mock(key=FakeKey(src)), viur_src_kind="wishlist", viur_delayed_update_tag=tag,
            )
            rel.key = FakeKey(f"rel-{i}")
            return rel

        # rel-1 and rel-2 share a tag (the key orders them); src-0 has a second relation on the last page
        relations = [
            relation(0, "src-0", self.NOW - 10), relation(1, "src-1", self.NOW - 9), relation(2, "src-2", self.NOW - 9),
            relation(3, "src-0", self.NOW - 8),
        ]
        page = self.PAGE

        class FakeQuery:
            """viur-relations ordered by (tag, key), a page at a time; like the datastore, a cursor only after a full
            page, as the position behind the last entry."""

            def __init__(self, kind):
                self.cutoff, self.cursor, self.last = None, None, None

            def filter(self, prop, value):
                if prop == "viur_delayed_update_tag <":
                    self.cutoff = value
                return self

            def setCursor(self, cursor):
                self.cursor = cursor
                return self

            def run(self):
                hits = sorted(
                    (r for r in relations if r["viur_delayed_update_tag"] < self.cutoff
                     and (self.cursor is None or (r["viur_delayed_update_tag"], r.key.name) > self.cursor)),
                    key=lambda r: (r["viur_delayed_update_tag"], r.key.name),
                )[:page]
                self.last = (hits[-1]["viur_delayed_update_tag"], hits[-1].key.name) if len(hits) == page else None
                return hits

            def getCursor(self):
                return self.last

        refreshed = []

        def patch(*args, key, **kwargs):
            if len(refreshed) > 10:
                raise AssertionError(f"refresh loop: {refreshed}")
            refreshed.append(key.name)
            for rel in relations:  # what RelationalBone.postSavedHandler does to the source's relations
                if rel["src"].key == key:
                    rel["viur_delayed_update_tag"] = self.NOW

        skel = mock.MagicMock()
        skel.patch.side_effect = patch
        update_relations = tasks.update_relations

        with mock.patch.object(tasks.db, "Query", FakeQuery), \
                mock.patch.object(tasks, "skeletonByKind", return_value=lambda: skel), \
                mock.patch.object(tasks.current, "request_data", mock.MagicMock()), \
                mock.patch.object(tasks.time, "time", return_value=self.NOW), \
                mock.patch.object(tasks, "update_relations",
                                  side_effect=lambda **kw: update_relations(**kw, _call_deferred=False)):
            update_relations(FakeKey("dest"), changed_bones=["name"], _call_deferred=False)

        self.assertEqual(["src-0", "src-1", "src-2"], refreshed)
