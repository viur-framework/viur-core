# TODO: Add more tests from https://github.com/viur-framework/viur-datastore/tree/master/tests

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
