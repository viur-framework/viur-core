"""IN/NOT_IN filter values given as a collection reach MongoDB as a list; BSON encodes no set."""
from abstract import ViURTestCase


class TestFilterCollections(ViURTestCase):

    def test_a_set_becomes_a_list(self):
        from viur.core.db.utils import to_mongo_filter
        flt = to_mongo_filter({"name IN": {"a"}, "name NOT_IN": frozenset({"b"})}, [])
        self.assertEqual({"name": {"$in": ["a"], "$nin": ["b"]}}, flt)

    def test_a_tuple_becomes_a_list(self):
        from viur.core.db.utils import to_mongo_filter
        self.assertEqual({"name": {"$in": ["a", "b"]}}, to_mongo_filter({"name IN": ("a", "b")}, []))

    def test_an_or_group_is_converted_as_well(self):
        from viur.core.db.utils import to_mongo_filter
        self.assertEqual({"$or": [{"name": {"$in": ["a"]}}]}, to_mongo_filter({}, [[("name IN", {"a"})]]))

    def test_the_filter_can_be_encoded(self):
        import bson
        from viur.core.db.utils import to_mongo_filter
        self.assertIsInstance(bson.encode(to_mongo_filter({"name IN": {"a", "b"}}, [])), bytes)
