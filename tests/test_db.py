# TODO: Add more tests from https://github.com/viur-framework/viur-datastore/tree/master/tests

import importlib
from unittest import mock

from abstract import ViURTestCase


class TestDb(ViURTestCase):
    def test_key_init(self) -> None:
        from viur.core import db
        key = db.Key("viur", 42)
        self.assertIsInstance(key.id, int)
        self.assertEqual(key.id, 42)
        self.assertIsNone(key.name)
        self.assertIsNone(key.parent)

        key = db.Key("viur", "1337")
        self.assertIsInstance(key.id, int)
        self.assertEqual(key.id, 1337)
        self.assertIsNone(key.name)
        self.assertIsNone(key.parent)

        key = db.Key("viur", "foo")
        self.assertEqual(key.name, "foo")
        self.assertIsNone(key.id)
        self.assertIsNone(key.parent)

        parent_key = db.Key("viur", "foo")
        key = db.Key("viur", "bar", parent=parent_key)
        self.assertEqual(key.name, "bar")
        self.assertEqual(key.parent, parent_key)


class TestEntryMatchesQuery(ViURTestCase):
    def _make_entity(self, **kwargs):
        from viur.core import db
        e = db.Entity(db.Key("Test", 1))
        for k, v in kwargs.items():
            e[k] = v
        return e

    def test_in_filter_matches(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        entry = self._make_entity(continent="Africa")
        self.assertTrue(_entryMatchesQuery(entry, {"continent IN": ["Africa", "Asia"]}))

    def test_in_filter_no_match(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        entry = self._make_entity(continent="Europe")
        self.assertFalse(_entryMatchesQuery(entry, {"continent IN": ["Africa", "Asia"]}))

    def test_neq_filter_matches(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        entry = self._make_entity(continent="Europe")
        self.assertTrue(_entryMatchesQuery(entry, {"continent !=": "Africa"}))

    def test_neq_filter_no_match(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        entry = self._make_entity(continent="Africa")
        self.assertFalse(_entryMatchesQuery(entry, {"continent !=": "Africa"}))

    def test_in_filter_multivalued_matches(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        # Entity with multiple continents — one is in the filter list
        entry = self._make_entity(continent=["Africa", "Europe"])
        self.assertTrue(_entryMatchesQuery(entry, {"continent IN": ["Africa", "Asia"]}))

    def test_in_filter_multivalued_no_match(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        # Entity with multiple continents — none is in the filter list
        entry = self._make_entity(continent=["Antarctica", "Europe"])
        self.assertFalse(_entryMatchesQuery(entry, {"continent IN": ["Africa", "Asia"]}))

    def test_not_in_filter_matches(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        entry = self._make_entity(continent="Europe")
        self.assertTrue(_entryMatchesQuery(entry, {"continent NOT_IN": ["Africa", "Asia"]}))

    def test_not_in_filter_no_match(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        entry = self._make_entity(continent="Africa")
        self.assertFalse(_entryMatchesQuery(entry, {"continent NOT_IN": ["Africa", "Asia"]}))


class TestRunSingleFilter(ViURTestCase):
    def test_in_filter_builds_single_property_filter(self) -> None:
        """IN filter must be passed as a single PropertyFilter with the list as value."""
        from unittest.mock import patch, MagicMock
        from viur.core.db.transport import run_single_filter
        from viur.core.db.types import QueryDefinition

        qdef = QueryDefinition(kind="Country", filters={"continent IN": ["Africa", "Asia"]}, orders=[])

        mock_fetch_result = MagicMock()
        mock_fetch_result.__iter__ = MagicMock(return_value=iter([]))
        mock_fetch_result.next_page_token = None
        mock_query = MagicMock()
        mock_client = MagicMock()
        mock_client.query.return_value = mock_query
        mock_query.fetch.return_value = mock_fetch_result

        with patch("viur.core.db.transport.__client__", mock_client):
            run_single_filter(qdef, limit=10, keys_only=False)

        from google.cloud.datastore.query import PropertyFilter
        mock_query.add_filter.assert_called_once()
        args, kwargs = mock_query.add_filter.call_args
        passed_filter = kwargs.get("filter") or args[0]
        self.assertIsInstance(passed_filter, PropertyFilter)
        self.assertEqual(passed_filter.property_name, "continent")
        self.assertEqual(passed_filter.operator, "IN")
        self.assertEqual(passed_filter.value, ["Africa", "Asia"])

    def test_not_in_filter_builds_single_property_filter(self) -> None:
        """NOT_IN filter must be passed as a single PropertyFilter with the list as value."""
        from unittest.mock import patch, MagicMock
        from viur.core.db.transport import run_single_filter
        from viur.core.db.types import QueryDefinition

        qdef = QueryDefinition(kind="Country", filters={"continent NOT_IN": ["Africa", "Asia"]}, orders=[])

        mock_fetch_result = MagicMock()
        mock_fetch_result.__iter__ = MagicMock(return_value=iter([]))
        mock_fetch_result.next_page_token = None
        mock_query = MagicMock()
        mock_client = MagicMock()
        mock_client.query.return_value = mock_query
        mock_query.fetch.return_value = mock_fetch_result

        with patch("viur.core.db.transport.__client__", mock_client):
            run_single_filter(qdef, limit=10, keys_only=False)

        from google.cloud.datastore.query import PropertyFilter
        mock_query.add_filter.assert_called_once()
        args, kwargs = mock_query.add_filter.call_args
        passed_filter = kwargs.get("filter") or args[0]
        self.assertIsInstance(passed_filter, PropertyFilter)
        self.assertEqual(passed_filter.property_name, "continent")
        self.assertEqual(passed_filter.operator, "NOT_IN")
        self.assertEqual(passed_filter.value, ["Africa", "Asia"])

    def test_neq_filter_builds_single_property_filter(self) -> None:
        """!= filter must be passed as a single PropertyFilter with a scalar value."""
        from unittest.mock import patch, MagicMock
        from viur.core.db.transport import run_single_filter
        from viur.core.db.types import QueryDefinition

        qdef = QueryDefinition(kind="Country", filters={"continent !=": "Africa"}, orders=[])

        mock_fetch_result = MagicMock()
        mock_fetch_result.__iter__ = MagicMock(return_value=iter([]))
        mock_fetch_result.next_page_token = None
        mock_query = MagicMock()
        mock_client = MagicMock()
        mock_client.query.return_value = mock_query
        mock_query.fetch.return_value = mock_fetch_result

        with patch("viur.core.db.transport.__client__", mock_client):
            run_single_filter(qdef, limit=10, keys_only=False)

        from google.cloud.datastore.query import PropertyFilter
        mock_query.add_filter.assert_called_once()
        args, kwargs = mock_query.add_filter.call_args
        passed_filter = kwargs.get("filter") or args[0]
        self.assertIsInstance(passed_filter, PropertyFilter)
        self.assertEqual(passed_filter.property_name, "continent")
        self.assertEqual(passed_filter.operator, "!=")
        self.assertEqual(passed_filter.value, "Africa")

    def test_or_filter_builds_or_composite_filter(self) -> None:
        """OR group must be passed as a single Or composite filter."""
        from unittest.mock import patch, MagicMock
        from viur.core.db.transport import run_single_filter
        from viur.core.db.types import QueryDefinition
        from google.cloud.datastore.query import Or, PropertyFilter

        qdef = QueryDefinition(
            kind="Country",
            filters={},
            orders=[],
            or_filters=[[("continent =", "Africa"), ("continent =", "Asia")]],
        )

        mock_fetch_result = MagicMock()
        mock_fetch_result.__iter__ = MagicMock(return_value=iter([]))
        mock_fetch_result.next_page_token = None
        mock_query = MagicMock()
        mock_client = MagicMock()
        mock_client.query.return_value = mock_query
        mock_query.fetch.return_value = mock_fetch_result

        with patch("viur.core.db.transport.__client__", mock_client):
            run_single_filter(qdef, limit=10, keys_only=False)

        mock_query.add_filter.assert_called_once()
        args, kwargs = mock_query.add_filter.call_args
        passed_filter = kwargs.get("filter") or args[0]
        self.assertIsInstance(passed_filter, Or)
        self.assertEqual(len(passed_filter.filters), 2)
        self.assertIsInstance(passed_filter.filters[0], PropertyFilter)
        self.assertEqual(passed_filter.filters[0].property_name, "continent")
        self.assertEqual(passed_filter.filters[0].value, "Africa")
        self.assertEqual(passed_filter.filters[1].value, "Asia")

    def test_two_or_groups_produce_two_add_filter_calls(self) -> None:
        """Two OR groups must produce two separate Or composite filter calls."""
        from unittest.mock import patch, MagicMock
        from viur.core.db.transport import run_single_filter
        from viur.core.db.types import QueryDefinition
        from google.cloud.datastore.query import Or

        qdef = QueryDefinition(
            kind="Country",
            filters={},
            orders=[],
            or_filters=[
                [("continent =", "Africa"), ("continent =", "Asia")],
                [("sortindex >", 100), ("sortindex <", 50)],
            ],
        )

        mock_fetch_result = MagicMock()
        mock_fetch_result.__iter__ = MagicMock(return_value=iter([]))
        mock_fetch_result.next_page_token = None
        mock_query = MagicMock()
        mock_client = MagicMock()
        mock_client.query.return_value = mock_query
        mock_query.fetch.return_value = mock_fetch_result

        with patch("viur.core.db.transport.__client__", mock_client):
            run_single_filter(qdef, limit=10, keys_only=False)

        self.assertEqual(mock_query.add_filter.call_count, 2)
        for call in mock_query.add_filter.call_args_list:
            args, kwargs = call
            passed_filter = kwargs.get("filter") or args[0]
            self.assertIsInstance(passed_filter, Or)


class TestQueryIterSkel(ViURTestCase):
    """Tests for Query.iter_skel(), the SkeletonInstance-counterpart of Query.iter()."""

    def _make_src_skel(self):
        """Build a minimal SkeletonInstance usable as srcSkel, without a Skeleton class on disk."""
        from viur.core.bones import KeyBone, StringBone
        from viur.core.skeleton import SkeletonInstance

        class FakeSkelCls:
            kindName = "test_iter_skel"
            __boneMap__ = {}

        key_bone, name_bone = KeyBone(), StringBone()
        key_bone.__set_name__(FakeSkelCls, "key")
        name_bone.__set_name__(FakeSkelCls, "name")

        return SkeletonInstance(FakeSkelCls, bone_map={"key": key_bone, "name": name_bone})

    def _make_entity(self, num: int, name: str):
        from viur.core import db
        entity = db.Entity(db.Key("test_iter_skel", num))
        entity["name"] = name
        return entity

    def test_yields_skeleton_instances_over_all_batches(self) -> None:
        """iter_skel() must yield one SkeletonInstance per entity, following the query cursor."""
        from unittest.mock import patch
        from viur.core import db
        from viur.core.skeleton import SkeletonInstance

        src_skel = self._make_src_skel()
        query = db.Query("test_iter_skel", src_skel)
        entities = [self._make_entity(1, "a"), self._make_entity(2, "b"), self._make_entity(3, "c")]

        batches = [(entities[:2], b"cursor"), (entities[2:], None)]

        def fake_run(queries, limit, keys_only):
            result, cursor = batches.pop(0)
            queries.currentCursor = cursor
            return result

        with patch.object(db.Query, "_run_single_filter_query", side_effect=fake_run):
            res = list(query.iter_skel())

        self.assertEqual(len(res), 3)
        for skel in res:
            self.assertIsInstance(skel, SkeletonInstance)
        self.assertEqual([skel["name"] for skel in res], ["a", "b", "c"])
        self.assertEqual([skel.dbEntity for skel in res], entities)

    def test_yields_distinct_instances(self) -> None:
        """Each result must be its own instance, so collecting or writing them is safe."""
        from unittest.mock import patch
        from viur.core import db

        src_skel = self._make_src_skel()
        query = db.Query("test_iter_skel", src_skel)
        entities = [self._make_entity(1, "a"), self._make_entity(2, "b")]

        def fake_run(queries, limit, keys_only):
            queries.currentCursor = None
            return entities

        with patch.object(db.Query, "_run_single_filter_query", side_effect=fake_run):
            res = list(query.iter_skel())

        self.assertEqual(len({id(skel) for skel in res}), 2)
        # The bone-map is shared with the source skeleton, the source skeleton itself is untouched
        self.assertTrue(all(skel.boneMap is src_skel.boneMap for skel in res))
        self.assertTrue(all(skel.skeletonCls is src_skel.skeletonCls for skel in res))
        self.assertIsNone(src_skel.dbEntity)

    def test_without_src_skel_raises_on_call(self) -> None:
        """A query not created by skel.all() must fail immediately, not on first iteration."""
        from viur.core import db
        with self.assertRaises(NotImplementedError):
            db.Query("test_iter_skel").iter_skel()

    def test_multi_query_raises_on_call(self) -> None:
        """Multi-queries cannot be iterated; the error must be raised immediately."""
        from viur.core import db
        query = db.Query("test_iter_skel", self._make_src_skel())
        query.queries = [query.queries, query.queries]
        with self.assertRaises(ValueError):
            query.iter_skel()

    def test_unsatisfiable_query_yields_nothing(self) -> None:
        """A query which cannot be satisfied must result in an empty iteration."""
        from viur.core import db
        query = db.Query("test_iter_skel", self._make_src_skel())
        query.queries = None
        self.assertEqual(list(query.iter_skel()), [])

    def test_iter_on_unsatisfiable_query_yields_nothing(self) -> None:
        """Query.iter() must end cleanly instead of raising RuntimeError (PEP 479)."""
        from viur.core import db
        query = db.Query("test_iter_skel")
        query.queries = None
        self.assertEqual(list(query.iter()), [])


class TestQueryFilter(ViURTestCase):
    def test_in_filter_does_not_create_multiquery(self) -> None:
        """IN filter must not create a multi-query (list of QueryDefinitions)."""
        from viur.core import db
        q = db.Query("Country")
        q.filter("continent IN", ["Africa", "Asia"])
        self.assertIsInstance(q.queries, db.QueryDefinition)
        self.assertIn("continent IN", q.queries.filters)
        self.assertEqual(q.queries.filters["continent IN"], ["Africa", "Asia"])

    def test_neq_filter_does_not_create_multiquery(self) -> None:
        """!= filter must not create a multi-query (list of QueryDefinitions)."""
        from viur.core import db
        q = db.Query("Country")
        q.filter("continent !=", "Africa")
        self.assertIsInstance(q.queries, db.QueryDefinition)
        self.assertIn("continent !=", q.queries.filters)
        self.assertEqual(q.queries.filters["continent !="], "Africa")

    def test_in_filter_lowercase_op_normalized(self) -> None:
        """Lowercase op 'in' must be normalized to 'IN'."""
        from viur.core import db
        q = db.Query("Country")
        q.filter("continent in", ["Africa", "Asia"])
        self.assertIsInstance(q.queries, db.QueryDefinition)
        self.assertIn("continent IN", q.queries.filters)

    def test_regular_filter_unchanged(self) -> None:
        """Regular equality filters must not be affected by the refactor."""
        from viur.core import db
        q = db.Query("Country")
        q.filter("continent =", "Africa")
        self.assertIsInstance(q.queries, db.QueryDefinition)
        self.assertEqual(q.queries.filters["continent ="], "Africa")

    def test_not_in_filter_does_not_create_multiquery(self) -> None:
        """NOT_IN filter must not create a multi-query (list of QueryDefinitions)."""
        from viur.core import db
        q = db.Query("Country")
        q.filter("continent NOT_IN", ["Africa", "Asia"])
        self.assertIsInstance(q.queries, db.QueryDefinition)
        self.assertIn("continent NOT_IN", q.queries.filters)
        self.assertEqual(q.queries.filters["continent NOT_IN"], ["Africa", "Asia"])

    def test_not_in_filter_lowercase_op_normalized(self) -> None:
        """Lowercase op 'not_in' must be normalized to 'NOT_IN'."""
        from viur.core import db
        q = db.Query("Country")
        q.filter("continent not_in", ["Africa", "Asia"])
        self.assertIsInstance(q.queries, db.QueryDefinition)
        self.assertIn("continent NOT_IN", q.queries.filters)


class TestQueryDefinitionOrFilters(ViURTestCase):
    def test_querydef_has_empty_or_filters_by_default(self) -> None:
        from viur.core import db
        qdef = db.QueryDefinition(kind="Test", filters={}, orders=[])
        self.assertEqual(qdef.or_filters, [])


class TestQueryOrFilter(ViURTestCase):
    def test_or_filter_stores_group_in_or_filters(self) -> None:
        from viur.core import db
        q = db.Query("Country")
        q.or_filter(("continent =", "Africa"), ("continent =", "Asia"))
        self.assertIsInstance(q.queries, db.QueryDefinition)
        self.assertEqual(len(q.queries.or_filters), 1)
        self.assertEqual(q.queries.or_filters[0], [
            ("continent =", "Africa"),
            ("continent =", "Asia"),
        ])

    def test_or_filter_multiple_calls_produce_multiple_groups(self) -> None:
        from viur.core import db
        q = db.Query("Country")
        q.or_filter(("continent =", "Africa"), ("continent =", "Asia"))
        q.or_filter(("sortindex >", 100), ("sortindex <", 50))
        self.assertEqual(len(q.queries.or_filters), 2)

    def test_or_filter_lowercase_op_normalized(self) -> None:
        from viur.core import db
        q = db.Query("Country")
        q.or_filter(("continent in", ["Africa", "Asia"]))
        self.assertEqual(q.queries.or_filters[0][0][0], "continent IN")

    def test_or_filter_no_space_defaults_to_equality(self) -> None:
        from viur.core import db
        q = db.Query("Country")
        q.or_filter(("continent", "Africa"))
        self.assertEqual(q.queries.or_filters[0][0][0], "continent =")

    def test_or_filter_not_in_op_normalized(self) -> None:
        from viur.core import db
        q = db.Query("Country")
        q.or_filter(("continent not_in", ["Africa", "Asia"]))
        self.assertEqual(q.queries.or_filters[0][0][0], "continent NOT_IN")

    def test_or_filter_chaining(self) -> None:
        from viur.core import db
        q = db.Query("Country")
        result = q.or_filter(("continent =", "Africa"), ("continent =", "Asia"))
        self.assertIs(result, q)
        result2 = result.or_filter(("sortindex >", 100))
        self.assertIs(result2, q)
        self.assertEqual(len(q.queries.or_filters), 2)


class TestEntryMatchesQueryOrFilters(ViURTestCase):
    def _make_entity(self, **kwargs):
        from viur.core import db
        e = db.Entity(db.Key("Test", 1))
        for k, v in kwargs.items():
            e[k] = v
        return e

    def test_or_group_matches_when_one_condition_is_true(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        entry = self._make_entity(continent="Africa")
        or_filters = [[("continent =", "Europe"), ("continent =", "Africa")]]
        self.assertTrue(_entryMatchesQuery(entry, {}, or_filters))

    def test_or_group_fails_when_no_condition_matches(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        entry = self._make_entity(continent="Antarctica")
        or_filters = [[("continent =", "Europe"), ("continent =", "Africa")]]
        self.assertFalse(_entryMatchesQuery(entry, {}, or_filters))

    def test_multiple_or_groups_are_anded(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        # continent matches group 1, but sortindex does not match group 2
        entry = self._make_entity(continent="Africa", sortindex=50)
        or_filters = [
            [("continent =", "Africa"), ("continent =", "Asia")],
            [("sortindex >", 100), ("sortindex <", 30)],
        ]
        self.assertFalse(_entryMatchesQuery(entry, {}, or_filters))

    def test_and_plus_or_filters_both_must_pass(self) -> None:
        from viur.core.db.query import _entryMatchesQuery
        entry = self._make_entity(continent="Africa", sortindex=200)
        self.assertTrue(_entryMatchesQuery(
            entry,
            {"sortindex >": 100},
            [[("continent =", "Africa"), ("continent =", "Asia")]],
        ))

class TestQueryOrder(ViURTestCase):
    def test_queryorder_is_namedtuple(self) -> None:
        from viur.core import db
        qo = db.QueryOrder("name")
        self.assertIsInstance(qo, tuple)
        self.assertEqual(qo.name, "name")
        self.assertEqual(qo.order, db.SortOrder.Ascending)  # default

    def test_queryorder_default_is_ascending(self) -> None:
        from viur.core import db
        self.assertEqual(db.QueryOrder("x").order, db.SortOrder.Ascending)

    def test_queryorder_tuple_compat(self) -> None:
        from viur.core import db
        qo = db.QueryOrder("age", db.SortOrder.Descending)
        # Index-Zugriff
        self.assertEqual(qo[0], "age")
        self.assertEqual(qo[1], db.SortOrder.Descending)
        # Tuple-Unpacking
        name, direction = qo
        self.assertEqual(name, "age")
        self.assertEqual(direction, db.SortOrder.Descending)

    def test_query_order_method_returns_queryorder(self) -> None:
        from viur.core import db
        q = db.Query("TestKind")
        q.order(("name", db.SortOrder.Ascending))
        orders = q.get_orders()
        self.assertIsNotNone(orders)
        self.assertIsInstance(orders[0], db.QueryOrder)
        self.assertEqual(orders[0].name, "name")
        self.assertEqual(orders[0].order, db.SortOrder.Ascending)

    def test_query_order_string_shortcut(self) -> None:
        from viur.core import db
        q = db.Query("TestKind")
        q.order("name")
        orders = q.get_orders()
        self.assertIsNotNone(orders)
        self.assertIsInstance(orders[0], db.QueryOrder)
        self.assertEqual(orders[0].name, "name")
        self.assertEqual(orders[0].order, db.SortOrder.Ascending)

    def test_query_order_plain_tuple_compat(self) -> None:
        from viur.core import db
        q = db.Query("TestKind")
        q.order(("age", db.SortOrder.Descending))
        orders = q.get_orders()
        self.assertIsNotNone(orders)
        self.assertIsInstance(orders[0], db.QueryOrder)


class TestNamedDatabase(ViURTestCase):
    """Covers the configurable named database/namespace support.

    See `conf.db.name` / `conf.db.namespace`: keys and the legacy urlsafe
    encoding must work while the process is wired to a non-default database.
    """

    @staticmethod
    def _fake_client(*, database=None, namespace=None):
        client = mock.Mock()
        client.project = "test-project"
        client.database = database
        client.namespace = namespace
        return client

    def test_key_inherits_database_and_namespace_from_client(self) -> None:
        from viur.core import db
        from viur.core.db import transport
        with mock.patch.object(
            transport, "__client__",
            self._fake_client(database="viur-tests", namespace="ns-ak"),
        ):
            key = db.Key("viur", 42)
        self.assertEqual(key.database, "viur-tests")
        self.assertEqual(key.namespace, "ns-ak")

    def test_explicit_key_argument_wins_over_client_default(self) -> None:
        from viur.core import db
        from viur.core.db import transport
        with mock.patch.object(
            transport, "__client__",
            self._fake_client(database="viur-tests", namespace="ns-ak"),
        ):
            key = db.Key("viur", 42, database="other-db", namespace="other-ns")
        self.assertEqual(key.database, "other-db")
        self.assertEqual(key.namespace, "other-ns")

    def test_default_client_keeps_keys_on_default_database(self) -> None:
        from viur.core import db
        from viur.core.db import transport
        with mock.patch.object(transport, "__client__", self._fake_client()):
            key = db.Key("viur", 42)
        self.assertIsNone(key.database)

    def test_to_legacy_urlsafe_tolerates_named_database(self) -> None:
        from viur.core import db
        from viur.core.db import transport
        with mock.patch.object(
            transport, "__client__", self._fake_client(database="viur-tests"),
        ):
            key = db.Key("viur", "foo")
            # Without the override both calls would raise ValueError.
            self.assertIsInstance(key.to_legacy_urlsafe(), bytes)
            self.assertIsInstance(str(key), str)

    def test_from_legacy_urlsafe_tolerates_named_database(self) -> None:
        from viur.core import db
        from viur.core.db import transport
        with mock.patch.object(
            transport, "__client__", self._fake_client(database="viur-tests", namespace="baz"),
        ):
            key = db.Key("viur", "foo")
            key_loaded = db.Key.from_legacy_urlsafe(key.to_legacy_urlsafe())
            self.assertEqual(key, key_loaded)
            self.assertEqual(key.database, key_loaded.database)
            self.assertEqual(key.namespace, key_loaded.namespace)
            self.assertEqual(key.project, key_loaded.project)
            self.assertEqual(key.id_or_name, key_loaded.id_or_name)

    def test_transport_builds_client_from_conf(self) -> None:
        from viur.core.config import conf
        from viur.core.db import transport
        try:
            with (
                mock.patch.object(conf.db, "name", "viur-tests"),
                mock.patch.object(conf.db, "namespace", "ns-ak"),
                mock.patch("google.cloud.datastore.Client") as MockClient,
            ):
                importlib.reload(transport)
                MockClient.assert_called_once_with(
                    database="viur-tests", namespace="ns-ak",
                )
        finally:
            # Restore the real, default-database client for the other tests.
            importlib.reload(transport)

    def test_transport_unconfigured_builds_default_client(self) -> None:
        from viur.core.db import transport
        try:
            with mock.patch("google.cloud.datastore.Client") as MockClient:
                importlib.reload(transport)
                MockClient.assert_called_once_with(database=None, namespace=None)
        finally:
            importlib.reload(transport)


class TestDbCache(ViURTestCase):
    """Tests for the memcache layer in front of the datastore (viur.core.db.cache)."""

    def setUp(self) -> None:
        super().setUp()
        from google.appengine.api.memcache import Client
        from viur.core.config import conf
        self.conf = conf
        # The testbed activated by ViURTestCase provides a memcache stub, so this
        # is a real client talking to an in-process cache.
        conf.db.memcache_client = Client()

    def tearDown(self) -> None:
        self.conf.db.memcache_client = None
        super().tearDown()

    @staticmethod
    def _entity(key_name: str, **values):
        from viur.core import db
        entity = db.Entity(db.Key("Auftrag", key_name))
        entity |= values
        return entity

    def test_get_returns_a_list_for_a_single_hit(self) -> None:
        """A single hit must not be returned as a bare Entity (which is dict-like and iterates its fields)."""
        from viur.core.db import cache
        entity = self._entity("A1", name="Test")
        cache.put(entity)

        result = cache.get(entity.key)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].key, entity.key)

    def test_get_returns_the_same_type_for_one_and_many_hits(self) -> None:
        from viur.core.db import cache
        one = self._entity("A1", name="Test")
        two = self._entity("A2", name="Test")
        cache.put([one, two])

        single = cache.get(one.key)
        multiple = cache.get([one.key, two.key])
        self.assertIs(type(single), type(multiple))
        self.assertEqual(len(multiple), 2)
        self.assertEqual({str(entity.key) for entity in multiple}, {str(one.key), str(two.key)})

    def test_get_returns_an_empty_list_on_a_miss(self) -> None:
        from viur.core.db import cache
        result = cache.get(self._entity("missing").key)
        self.assertIsInstance(result, list)
        self.assertFalse(result)

    def test_round_trip_preserves_key_and_values(self) -> None:
        """put() stores under str(key), get() decodes it again — both must agree on the encoding."""
        from viur.core.db import cache
        entity = self._entity("A1", name="Test", number=42)
        cache.put(entity)

        (cached,) = cache.get(entity.key)
        self.assertEqual(cached.key, entity.key)
        self.assertEqual(cached.key.kind, "Auftrag")
        self.assertEqual(cached.key.name, "A1")
        self.assertEqual(cached["name"], "Test")
        self.assertEqual(cached["number"], 42)

    def test_get_without_memcache_client_returns_an_empty_list(self) -> None:
        from viur.core.db import cache
        self.conf.db.memcache_client = None
        result = cache.get(self._entity("A1").key)
        self.assertIsInstance(result, list)
        self.assertFalse(result)

    def test_get_is_skipped_inside_a_transaction(self) -> None:
        from viur.core.db import cache
        entity = self._entity("A1", name="Test")
        cache.put(entity)

        with mock.patch("viur.core.db.utils.is_in_transaction", return_value=True):
            result = cache.get(entity.key)
        self.assertIsInstance(result, list)
        self.assertFalse(result)

    def test_put_is_skipped_inside_a_transaction(self) -> None:
        from viur.core.db import cache
        entity = self._entity("A1", name="Test")

        with mock.patch("viur.core.db.utils.is_in_transaction", return_value=True):
            self.assertFalse(cache.put(entity))
        self.assertFalse(cache.get(entity.key))

    def test_db_get_serves_a_warm_cache_without_hitting_the_datastore(self) -> None:
        from viur.core.db import cache, transport
        entity = self._entity("A1", name="Test")
        cache.put(entity)

        with mock.patch.object(transport.__client__, "get_multi") as get_multi:
            result = transport.get(entity.key)

        get_multi.assert_not_called()
        self.assertEqual(result.key, entity.key)
        self.assertEqual(result["name"], "Test")

    def test_db_get_of_a_key_list_serves_a_warm_cache(self) -> None:
        from viur.core.db import cache, transport
        one = self._entity("A1", name="one")
        two = self._entity("A2", name="two")
        cache.put([one, two])

        with mock.patch.object(transport.__client__, "get_multi") as get_multi:
            result = transport.get([one.key, two.key])

        get_multi.assert_not_called()
        self.assertEqual([entity.key for entity in result], [one.key, two.key])

    def test_db_get_falls_back_to_the_datastore_and_warms_the_cache(self) -> None:
        from viur.core.db import cache, transport
        entity = self._entity("A1", name="Test")

        with mock.patch.object(transport.__client__, "get_multi", return_value=[entity]) as get_multi:
            result = transport.get(entity.key)

        get_multi.assert_called_once_with([entity.key])
        self.assertEqual(result.key, entity.key)
        (cached,) = cache.get(entity.key)
        self.assertEqual(cached.key, entity.key)

    def test_db_get_mixes_cached_and_fetched_entities_in_key_order(self) -> None:
        from viur.core.db import cache, transport
        cached_entity = self._entity("A1", name="cached")
        fetched_entity = self._entity("A2", name="fetched")
        cache.put(cached_entity)

        with mock.patch.object(
            transport.__client__, "get_multi", return_value=[fetched_entity],
        ) as get_multi:
            result = transport.get([fetched_entity.key, cached_entity.key])

        get_multi.assert_called_once_with([fetched_entity.key])
        self.assertEqual([entity["name"] for entity in result], ["fetched", "cached"])

    def test_db_get_inside_a_transaction_bypasses_the_cache(self) -> None:
        from viur.core.db import cache, transport
        entity = self._entity("A1", name="Test")
        cache.put(entity)

        with (
            mock.patch("viur.core.db.utils.is_in_transaction", return_value=True),
            mock.patch.object(transport.__client__, "get_multi", return_value=[entity]) as get_multi,
        ):
            result = transport.get(entity.key)

        get_multi.assert_called_once_with([entity.key])
        self.assertEqual(result.key, entity.key)

    def test_db_put_caches_only_after_the_datastore_write_succeeded(self) -> None:
        """A failed datastore write must not leave an unpersisted value in the cache."""
        from viur.core.db import cache, transport
        entity = self._entity("A1", name="Test")

        with mock.patch.object(transport.__client__, "put", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                transport.put(entity)

        self.assertFalse(cache.get(entity.key))

    def test_db_put_warms_the_cache(self) -> None:
        from viur.core.db import cache, transport
        entity = self._entity("A1", name="Test")

        with mock.patch.object(transport.__client__, "put"):
            transport.put(entity)

        (cached,) = cache.get(entity.key)
        self.assertEqual(cached.key, entity.key)
        self.assertEqual(cached["name"], "Test")

    def test_db_delete_drops_the_entity_from_the_cache(self) -> None:
        from viur.core.db import cache, transport
        entity = self._entity("A1", name="Test")
        cache.put(entity)

        with mock.patch.object(transport.__client__, "delete"):
            transport.delete(entity.key)

        self.assertFalse(cache.get(entity.key))
