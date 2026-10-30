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

    def test_query_count_default_up_to(self) -> None:
        """The default ``up_to`` of ``Query.count`` must be a valid aggregation limit (Int32)."""
        from unittest import mock
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import datastore
        from viur.core import db

        with mock.patch("viur.core.db.query.count", return_value=42) as transport_count:
            self.assertEqual(db.Query("viur").count(), 42)
        up_to = transport_count.call_args.kwargs["up_to"]

        # Build the aggregation request like the transport does, without sending it
        client = datastore.Client(project="test", credentials=AnonymousCredentials())
        result = client.aggregation_query(client.query(kind="viur")).count(alias="total").fetch(limit=up_to)
        result._build_protobuf()  # raises ValueError for a limit beyond Int32
