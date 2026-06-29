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
                MockClient.assert_called_once_with()
        finally:
            importlib.reload(transport)

    def test_banner_omits_lines_for_default_database(self) -> None:
        import viur.core
        from viur.core.config import conf
        with (
            mock.patch.object(conf.db, "name", None),
            mock.patch.object(conf.db, "namespace", None),
        ):
            self.assertEqual(viur.core._datastore_banner_lines(), [])

    def test_banner_shows_named_database_and_namespace(self) -> None:
        import viur.core
        from viur.core.config import conf
        with (
            mock.patch.object(conf.db, "name", "viur-tests"),
            mock.patch.object(conf.db, "namespace", "ns-ak"),
        ):
            lines = viur.core._datastore_banner_lines()
        self.assertTrue(any("database = " in line and "viur-tests" in line for line in lines))
        self.assertTrue(any("namespace = " in line and "ns-ak" in line for line in lines))
