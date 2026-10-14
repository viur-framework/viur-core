"""Tests for computed bones: Always, Lifetime, Once, OnWrite."""
import datetime
import logging
from unittest import mock

from tests.abstract import ViURTestCase

TestSkel = None  # assigned in setUpModule


def _increase_counter(skel, bone_name):
    logging.info(f"{bone_name!r} = {skel[bone_name]!r}")
    return (skel[bone_name] or 0) + 1


def setUpModule():
    global TestSkel

    from viur.core import bones, db, conf  # noqa: F401
    from viur.core.bones.base import Compute, ComputeInterval, ComputeMethod
    from viur.core import skeleton

    if "/tests/" not in conf.skeleton_search_path:
        conf.skeleton_search_path = list(conf.skeleton_search_path) + ["/tests/"]

    class _TestSkel(skeleton.Skeleton):
        kindName = "test-compute"

        name = bones.StringBone()

        counter_always = bones.NumericBone(
            compute=Compute(_increase_counter),
        )

        counter_lifetime = bones.NumericBone(
            compute=Compute(
                _increase_counter,
                ComputeInterval(ComputeMethod.Lifetime, datetime.timedelta(seconds=30)),
            ),
        )

        counter_once = bones.NumericBone(
            compute=Compute(
                _increase_counter,
                ComputeInterval(ComputeMethod.Once),
            ),
        )

        counter_onwrite = bones.NumericBone(
            compute=Compute(
                _increase_counter,
                ComputeInterval(ComputeMethod.OnWrite),
            ),
        )

    TestSkel = _TestSkel


def _entity(**fields):
    from viur.core import db
    e = db.Entity(db.Key(TestSkel.kindName, "e1"))
    for k, v in fields.items():
        e[k] = v
    return e


def _write(skel, stored=None):
    """Run skel.write() with a mocked datastore and return the written entity."""
    from viur.core import db
    from viur.core.skeleton import tasks

    written = []
    key = db.Key(TestSkel.kindName, "e1")

    def get(db_key):
        if db_key.kind == TestSkel.kindName:
            return stored
        return None

    with mock.patch.object(db, "allocate_ids", return_value=[key]), \
            mock.patch.object(db, "get", side_effect=get), \
            mock.patch.object(db, "put", side_effect=written.append), \
            mock.patch.object(db, "is_in_transaction", return_value=True), \
            mock.patch.object(tasks, "update_relations", mock.Mock()):
        print("SKEL WRITE DU HURE"*33)
        skel.write()

    return next(e for e in written if e.key.kind == TestSkel.kindName)


class TestComputeAlways(ViURTestCase):
    """ComputeMethod.Always - recomputes on every read."""

    def test_fresh_skel_starts_at_one(self):
        skel = TestSkel()
        self.assertEqual(1, skel["counter_always"])

    def test_increments_value_loaded_from_db(self):
        skel = TestSkel()
        skel.setEntity(_entity(counter_always=5))
        self.assertEqual(6, skel["counter_always"])

    def test_computed_value_is_persisted_on_write(self):
        skel = TestSkel()
        entity = _write(skel)
        print("FICKER"*33)
        print(entity)
        self.assertEqual(1, entity["counter_always"])


class TestComputeLifetime(ViURTestCase):
    """ComputeMethod.Lifetime - recomputes only after the configured interval elapses."""

    _T0 = datetime.datetime(2020, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)

    def test_fresh_skel_computes_immediately(self):
        skel = TestSkel()
        self.assertEqual(1, skel["counter_lifetime"])

    def test_within_lifetime_returns_stored_value(self):
        from viur.core import utils
        skel = TestSkel()
        skel.setEntity(_entity(counter_lifetime=5, **{"_viur_compute_counter_lifetime_": self._T0}))
        with mock.patch.object(utils, "utcNow", return_value=self._T0 + datetime.timedelta(seconds=10)):
            self.assertEqual(5, skel["counter_lifetime"])

    def test_expired_lifetime_recomputes_on_read(self):
        from viur.core import db, utils
        entity = _entity(counter_lifetime=5, **{"_viur_compute_counter_lifetime_": self._T0})
        skel = TestSkel()
        skel.setEntity(entity)
        expired = self._T0 + datetime.timedelta(minutes=5)
        with mock.patch.object(utils, "utcNow", return_value=expired), \
                mock.patch.object(db, "is_in_transaction", return_value=True), \
                mock.patch.object(db, "get", return_value=entity), \
                mock.patch.object(db, "put", mock.Mock()):
            self.assertEqual(6, skel["counter_lifetime"])


class TestComputeOnce(ViURTestCase):
    """ComputeMethod.Once - computed on the first write, frozen on all subsequent writes."""

    def test_not_computed_before_first_write(self):
        skel = TestSkel()
        self.assertIsNone(skel["counter_once"])

    def test_value_is_fixed_after_first_write(self):
        # first write - bone absent from the DB, so it gets computed
        skel = TestSkel()
        written = _write(skel)
        self.assertEqual(1, written["counter_once"])

        # second write - bone is now stored, value must not change
        skel = TestSkel()
        skel.setEntity(written)
        written = _write(skel, stored=written)
        self.assertEqual(1, written["counter_once"])

        # third write - still frozen
        skel = TestSkel()
        skel.setEntity(written)
        written = _write(skel, stored=written)
        self.assertEqual(1, written["counter_once"])


class TestComputeOnWrite(ViURTestCase):
    """ComputeMethod.OnWrite - not recomputed on read; recomputed on every write."""

    def test_read_returns_stored_value_unchanged(self):
        skel = TestSkel()
        skel.setEntity(_entity(counter_onwrite=5))
        self.assertEqual(5, skel["counter_onwrite"])

    def test_increments_on_every_write(self):
        # first write - starts at None, becomes 1
        skel = TestSkel()
        written = _write(skel)
        self.assertEqual(1, written["counter_onwrite"])

        # second write - reads stored 1, becomes 2
        skel = TestSkel()
        skel.setEntity(written)
        written = _write(skel, stored=written)
        self.assertEqual(2, written["counter_onwrite"])

        # third write - reads stored 2, becomes 3
        skel = TestSkel()
        skel.setEntity(written)
        written = _write(skel, stored=written)
        self.assertEqual(3, written["counter_onwrite"])
