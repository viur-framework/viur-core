from unittest import mock

from abstract import ViURTestCase


class FakeSkel(dict):
    """Minimal stand-in for the skeleton returned by ``ModuleConf.addSkel()``."""

    def __init__(self, sink: list):
        super().__init__()
        self._sink = sink

    def write(self, *args, **kwargs):
        self._sink.append(self["name"])


class TestReadAllModules(ViURTestCase):
    """Regression tests for :meth:`ModuleConf.read_all_modules`."""

    def setUp(self):
        super().setUp()
        from viur.core.modules.moduleconf import ModuleConf
        ModuleConf.MODULES.clear()

    def _collect_written(self, in_db: list[str], in_code: list[str]) -> list[str]:
        """Run ``read_all_modules()`` against a faked datastore and module tree.

        :param in_db: module names that already have a ``viur-module-conf`` entry.
        :param in_code: module names the application exposes below ``vi``.
        :return: the module names a new entry was written for.
        """
        from viur.core import Module, conf
        from viur.core.modules.moduleconf import ModuleConf

        written = []

        class Vi:
            pass

        vi = Vi()
        for name in in_code:
            setattr(vi, name, Module(name, name))

        # not a Module instance, so collect_modules() skips it -- just like at runtime
        vi._moduleconf = mock.Mock()
        vi._moduleconf.addSkel = lambda: FakeSkel(written)

        main_app = mock.Mock()
        main_app.vi = vi

        fake_db = mock.MagicMock()
        fake_db.Query.return_value.run.return_value = [{"name": name} for name in in_db]

        with mock.patch.object(conf, "main_app", main_app), \
                mock.patch("viur.core.modules.moduleconf.db", fake_db):
            ModuleConf.read_all_modules()

        return written

    def test_missing_module_is_created(self):
        """A module without a `viur-module-conf` entry gets one."""
        self.assertEqual(self._collect_written(in_db=[], in_code=["alpha"]), ["alpha"])

    def test_known_modules_are_left_alone(self):
        """Modules that already have an entry must not be written again."""
        self.assertEqual(self._collect_written(in_db=["alpha", "beta"], in_code=["alpha", "beta"]), [])

    def test_known_module_after_missing_one_is_left_alone(self):
        """A missing module must not cause the modules checked after it to be rewritten.

        ``read_all_modules()`` tests every module name against the names already
        stored in the datastore. When that collection is consumed by the test --
        as a generator expression is -- the first unknown module exhausts it, and
        every module checked afterwards looks unknown as well. Those entries are
        then overwritten with a blank skeleton, silently discarding whatever an
        application stores on its ``ModuleConfSkel`` subclass.
        """
        written = self._collect_written(in_db=["alpha", "gamma"], in_code=["alpha", "beta", "gamma"])
        self.assertEqual(written, ["beta"])

    def test_lookup_is_order_independent(self):
        """Known modules are recognized regardless of the order they are checked in.

        ``dir()`` yields the module names sorted, so a datastore query returning
        them in key order happens to line up. Nothing guarantees that, and the
        lookup must not depend on it.
        """
        written = self._collect_written(in_db=["gamma", "alpha"], in_code=["alpha", "beta", "gamma"])
        self.assertEqual(written, ["beta"])
