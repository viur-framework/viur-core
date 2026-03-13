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
