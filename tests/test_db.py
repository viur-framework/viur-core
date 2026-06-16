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
