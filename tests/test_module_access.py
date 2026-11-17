"""
Tests for the access names of (nested) modules:
  register_access_rights(), Module.access_right(), the can*-checks of the prototypes
  and the role-based access rights computed by UserSkel.write().
"""
from unittest import mock

from abstract import ViURTestCase


def _build_tree():
    """Build a module tree like ``conf.main_app.vi``: a top-level module and a module with sub-modules.

    ``shop.order`` points back to its parent, as nested modules often do.
    """
    from viur.core import Module

    class Rights(Module):
        handler = "list"
        accessRights = ("add", "edit", "view", "delete")
        roles = {
            "admin": "*",
            "editor": ("add", "edit"),
            "viewer": "view",
        }

    class Shop(Module):
        roles = {"admin": "*"}  # no handler and no accessRights

    vi = Module("vi", "/vi")
    vi.file = Rights("file", "/vi/file")
    vi.shop = Shop("shop", "/vi/shop")
    vi.shop.order = Rights("order", "/vi/shop/order")
    vi.shop.order.shop = vi.shop
    vi.shop.order.export = Module("export", "/vi/shop/order/export")
    vi.shop._update_methods()
    vi.shop.order._update_methods()
    vi._internal = Rights("_internal", "/vi/_internal")
    return vi


class TestRegisterAccessRights(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core import conf
        self._access_rights = list(conf.user.access_rights)

    def tearDown(self):
        from viur.core import conf
        conf.user.access_rights = self._access_rights
        super().tearDown()

    def test_module_init_does_not_register_rights(self):
        """Rights are named after the module tree has been built, not by the constructor."""
        from viur.core import conf
        vi = _build_tree()
        self.assertNotIn("order-edit", conf.user.access_rights)
        self.assertIsNone(vi.shop.order.access_name)

    def test_access_names_follow_the_module_tree(self):
        from viur.core.module import iter_modules, register_access_rights
        vi = _build_tree()
        register_access_rights(vi)

        self.assertEqual(vi.file.access_name, "file")
        self.assertEqual(vi.shop.access_name, "shop")
        self.assertEqual(vi.shop.order.access_name, "shop.order")
        self.assertEqual(vi.shop.order.export.access_name, "shop.order.export")
        # the back-reference to the parent is not followed
        self.assertEqual(
            [path for path, _ in iter_modules(vi)],
            ["file", "shop", "_internal", "shop.order", "shop.order.export"],
        )

    def test_registered_rights(self):
        from viur.core import conf
        from viur.core.module import register_access_rights
        vi = _build_tree()
        register_access_rights(vi)

        for right in ("add", "edit", "view", "delete"):
            self.assertIn(f"file-{right}", conf.user.access_rights)
            self.assertIn(f"shop.order-{right}", conf.user.access_rights)

        self.assertNotIn("order-edit", conf.user.access_rights)
        self.assertFalse([right for right in conf.user.access_rights if right.startswith("shop-")])
        # internal modules like _translation have access rights as well
        self.assertIn("_internal-edit", conf.user.access_rights)

    def test_explicit_access_name_is_kept(self):
        from viur.core import conf
        from viur.core.module import register_access_rights
        vi = _build_tree()
        vi.shop.order.access_name = "order"
        register_access_rights(vi)

        self.assertEqual(vi.shop.order.access_right("edit"), "order-edit")
        self.assertIn("order-edit", conf.user.access_rights)
        self.assertNotIn("shop.order-edit", conf.user.access_rights)

    def test_access_right_falls_back_to_module_name(self):
        """A module outside the module tree keeps the old naming."""
        from viur.core import Module
        self.assertEqual(Module("foo", "/foo").access_right("view"), "foo-view")

    def test_describe_lists_access_rights(self):
        from viur.core.module import register_access_rights
        vi = _build_tree()
        register_access_rights(vi)

        self.assertEqual(
            vi.shop.order.describe()["access_rights"],
            ["shop.order-add", "shop.order-edit", "shop.order-view", "shop.order-delete"],
        )


class TestPrototypeChecks(ViURTestCase):

    def _list_module(self, access_name: str | None):
        from viur.core.prototypes.list import List

        module = List("order", "/vi/shop/order")
        module.access_name = access_name
        return module

    def _with_user(self, access: list[str], func):
        from viur.core import current
        current.user.set({"access": access})
        return func()

    def test_list_checks_use_access_name(self):
        module = self._list_module("shop.order")
        self.assertTrue(self._with_user(["shop.order-add"], module.canAdd))
        self.assertFalse(self._with_user(["order-add"], module.canAdd))
        self.assertTrue(self._with_user(["shop.order-edit"], module.canPreview))
        self.assertTrue(self._with_user(["shop.order-edit"], lambda: module.canEdit({})))
        self.assertTrue(self._with_user(["shop.order-delete"], lambda: module.canDelete({})))
        self.assertFalse(self._with_user(["order-delete"], lambda: module.canDelete({})))


class TestRolesOfNestedModules(ViURTestCase):

    def _access_for(self, roles: list[str]) -> set[str]:
        from viur.core import conf
        from viur.core.module import register_access_rights
        from viur.core.modules.user import UserSkel
        from viur.core.skeleton import Skeleton

        vi = _build_tree()
        register_access_rights(vi)
        vi.user = mock.Mock()
        vi.user.get_role_defaults = lambda role: {"admin"}

        main_app = mock.Mock()
        main_app.vi = vi

        skel = {"roles": roles, "access": []}
        with mock.patch.object(conf, "main_app", main_app), \
                mock.patch.object(Skeleton, "write", lambda skel, *args, **kwargs: skel):
            UserSkel.write(skel)

        return set(skel["access"])

    def test_editor(self):
        self.assertEqual(
            self._access_for(["editor"]),
            {"admin", "file-add", "file-edit", "file-view", "shop.order-add", "shop.order-edit", "shop.order-view"},
        )

    def test_admin_without_access_rights(self):
        """A module with roles but without accessRights (``shop``) must not break the computation."""
        access = self._access_for(["admin"])
        self.assertIn("shop.order-delete", access)
        self.assertFalse([right for right in access if right.startswith("shop-")])
        self.assertFalse([right for right in access if right.startswith("_internal-")])
