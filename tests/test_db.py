# TODO: Add more tests from https://github.com/viur-framework/viur-datastore/tree/master/tests

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


class TestKeyDatabaseAgnostic(ViURTestCase):
    """
    Verify the database-agnostic Key design:
    - database is never stored on the key (_database always None)
    - Key.database reads from the active transport client
    - str(key) / to_legacy_urlsafe() works regardless of the named database
    - Key.to_protobuf() injects partition_id.database_id from the client
    - key_from_protobuf strips database_id from server responses
    - passing database= to Key.__init__ is silently dropped
    """

    def _mock_client(self, database=None):
        """Return a mock transport client with the given database."""
        import viur.core.db.transport as transport
        client = mock.MagicMock()
        client.project = "test-project"
        client.database = database
        return mock.patch.object(transport, "__client__", client)

    def test_database_property_reflects_client(self):
        from viur.core import db
        with self._mock_client(database=None):
            key = db.Key("kind", 1)
            self.assertIsNone(key.database)

        with self._mock_client(database="test"):
            key = db.Key("kind", 1)
            self.assertEqual(key.database, "test")

    def test_database_kwarg_is_dropped(self):
        """database= passed to Key.__init__ must not be stored."""
        from viur.core import db
        with self._mock_client(database="test"):
            key = db.Key("kind", 1, database="other")
            # _database must be None; Key.database reads from client
            self.assertIsNone(key._database)
            self.assertEqual(key.database, "test")

    def test_str_works_for_default_database(self):
        from viur.core import db
        with self._mock_client(database=None):
            key = db.Key("kind", 1)
            s = str(key)
            self.assertIsInstance(s, str)
            self.assertTrue(len(s) > 0)

    def test_str_works_for_named_database(self):
        """str(key) must not raise even when the client uses a named database."""
        from viur.core import db
        with self._mock_client(database="test"):
            key = db.Key("kind", 1)
            s = str(key)
            self.assertIsInstance(s, str)
            self.assertTrue(len(s) > 0)

    def test_str_is_same_regardless_of_database(self):
        """Key string representation is database-agnostic."""
        from viur.core import db
        with self._mock_client(database=None):
            s_default = str(db.Key("kind", 42))
        with self._mock_client(database="test"):
            s_named = str(db.Key("kind", 42))
        self.assertEqual(s_default, s_named)

    def test_to_protobuf_sets_database_id_for_named_db(self):
        """Key.to_protobuf() must include partition_id.database_id for named databases."""
        from viur.core import db
        with self._mock_client(database="test"):
            key = db.Key("kind", 1)
            pb = key.to_protobuf()
            self.assertEqual(pb._pb.partition_id.database_id, "test")

    def test_to_protobuf_no_database_id_for_default_db(self):
        """For the default database, partition_id.database_id must stay empty."""
        from viur.core import db
        with self._mock_client(database=None):
            key = db.Key("kind", 1)
            pb = key.to_protobuf()
            self.assertEqual(pb._pb.partition_id.database_id, "")

    def test_key_from_protobuf_strips_database_id(self):
        """Keys reconstructed from server protos must be database-agnostic."""
        from google.cloud.datastore_v1.types import entity as entity_pb2
        from viur.core.db.overrides import key_from_protobuf

        # Build a proto as the server would return it for a named database
        pb = entity_pb2.Key()._pb
        pb.partition_id.project_id = "test-project"
        pb.partition_id.database_id = "test"
        elem = pb.path.add()
        elem.kind = "kind"
        elem.id = 99

        with self._mock_client(database="test"):
            key = key_from_protobuf(pb)

        # _database must be None regardless of what was in the proto
        self.assertIsNone(key._database)
        self.assertEqual(key.kind, "kind")
        self.assertEqual(key.id, 99)
