"""/vi/, the former admin namespace, serves the very same routes as /json/."""
import types

from abstract import ViURTestCase


class TestViAlias(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core import conf
        for name in ("main_resolver", "main_app"):
            self.addCleanup(setattr, conf, name, getattr(conf, name))

    def _build(self, **modules):
        import viur.core
        from viur.core import render
        getattr(viur.core, "__build_app")(types.SimpleNamespace(**modules), render, "html")

    def _shop(self):
        from viur.core import Module, action

        class Shop(Module):
            json = True

            @action
            def view(self):
                pass

        return Shop

    def test_vi_is_the_json_node(self):
        from viur.core import conf
        self._build(shop=self._shop())

        self.assertIs(conf.main_resolver["json"], conf.main_resolver["vi"])
        self.assertIn("view", conf.main_resolver["vi"]["shop"])

    def test_a_module_cannot_be_named_vi(self):
        with self.assertRaises(NameError):
            self._build(vi=self._shop())
