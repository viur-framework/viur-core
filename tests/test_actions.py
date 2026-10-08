"""Actions: every exposed method of a Module, with can/on/then/skel hooks resolved at class creation."""
from abstract import ViURTestCase


class TestResolveHookNames(ViURTestCase):

    def test_a_single_word_action(self):
        from viur.core.actions import resolve_hook_names
        self.assertEqual(("canEdit", "onEdit", "thenEdit", "editSkel"), resolve_hook_names("edit"))

    def test_a_snake_case_action_becomes_pascal_and_camel_case(self):
        from viur.core.actions import resolve_hook_names
        self.assertEqual(
            ("canAddOrEdit", "onAddOrEdit", "thenAddOrEdit", "addOrEditSkel"),
            resolve_hook_names("add_or_edit"),
        )

    def test_a_camel_case_action_keeps_its_inner_capitals(self):
        from viur.core.actions import resolve_hook_names
        self.assertEqual(
            ("canGetAuthMethods", "onGetAuthMethods", "thenGetAuthMethods", "getAuthMethodsSkel"),
            resolve_hook_names("getAuthMethods"),
        )


class TestModuleActions(ViURTestCase):

    def _module(self):
        from viur.core import Module, action, exposed, internal_exposed

        class Shop(Module):
            @action
            def publish(self, key):
                skel = {"key": key}
                if not self.canPublish(skel):
                    return "denied"
                self.onPublish(skel)
                self.thenPublish(skel)
                return "published"

            @action
            @internal_exposed
            def recount(self):
                return self.canRecount(None)

            @exposed
            def info(self):
                return "a free endpoint"

            def helper(self):
                return "not exposed at all"

        return Shop

    def test_only_action_methods_are_actions(self):
        self.assertEqual({"publish", "recount"}, set(self._module()._actions))

    def test_an_action_is_exposed_and_stays_internal_over_internal_exposed(self):
        shop = self._module()
        self.assertIs(True, shop.publish.exposed)
        self.assertIs(False, shop.recount.exposed)

    def test_a_plain_exposed_endpoint_gets_no_hooks(self):
        shop = self._module()
        self.assertTrue(shop.info.exposed)
        self.assertFalse(hasattr(shop, "canInfo"))
        self.assertEqual("a free endpoint", shop("shop", "/shop").info())

    def test_an_override_with_exposed_is_no_action(self):
        from viur.core import exposed

        class Shop(self._module()):
            @exposed
            def publish(self, key):
                return "free"

        self.assertNotIn("publish", Shop._actions)

    def test_a_missing_can_hook_is_fail_closed(self):
        module = self._module()("shop", "/shop")
        with self.assertRaises(NotImplementedError):
            module.publish("k")

    def test_missing_hooks_fall_back_to_can_on_then(self):
        calls = []

        class Shop(self._module()):
            def can(self, skel):
                calls.append(("can", skel["key"]))
                return True

            def on(self, skel):
                calls.append(("on", skel["key"]))

            def then(self, skel):
                calls.append(("then", skel["key"]))

        self.assertEqual("published", Shop("shop", "/shop").publish("k"))
        self.assertEqual([("can", "k"), ("on", "k"), ("then", "k")], calls)

    def test_an_action_specific_hook_wins_over_the_fallback(self):
        class Shop(self._module()):
            def can(self, skel):
                return True

            def canPublish(self, skel):
                return False

        self.assertEqual("denied", Shop("shop", "/shop").publish("k"))

    def test_a_fallback_defined_in_a_further_subclass_is_used(self):
        class Shop(self._module()):
            pass

        class OpenShop(Shop):
            def can(self, skel):
                return True

        self.assertTrue(OpenShop("shop", "/shop").recount())

    def test_an_inherited_specific_hook_is_not_replaced_by_an_alias(self):
        class Shop(self._module()):
            def canPublish(self, skel):
                return True

        class SubShop(Shop):
            pass

        self.assertIs(Shop.canPublish, SubShop.canPublish)

    def test_on_and_then_do_nothing_by_default(self):
        module = self._module()("shop", "/shop")
        self.assertIsNone(module.on(None))
        self.assertIsNone(module.then(None))


class TestActionDecorator(ViURTestCase):

    def test_the_label_is_published_while_the_method_runs(self):
        from viur.core import Module, action, current, exposed

        class Feedback(Module):
            @action("feedback")
            @exposed
            def compose(self):
                return current.action.get()

        self.assertEqual("feedback", Feedback("feedback", "/feedback").compose())
        self.assertIsNone(current.action.get())

    def test_without_a_label_nothing_is_published(self):
        from viur.core import Module, current, exposed

        class Feedback(Module):
            @exposed
            def compose(self):
                return current.action.get()

        self.assertIsNone(Feedback("feedback", "/feedback").compose())

    def test_steps_follow_order_then_declaration(self):
        from viur.core import Module, action, exposed

        class Wizard(Module):
            @action(icon="person", icon_library="bootstrap", label="Contact", order=2)
            @exposed
            def contact(self):
                pass

            @action(icon="pencil", icon_library="bootstrap", label="Compose", order=1)
            @exposed
            def compose(self):
                pass

            @exposed
            def hidden(self):
                pass

        steps = Wizard("wizard", "/json/wizard").steps()
        self.assertEqual(["compose", "contact"], list(steps))
        self.assertEqual(
            {"icon": "pencil", "icon_library": "bootstrap", "label": "Compose", "url": "/json/wizard/compose"},
            steps["compose"].to_dict(),
        )


class TestEveryCoreActionIsAuthorized(ViURTestCase):
    """Every endpoint of the core is an action with its own can-hook, which its body calls first."""

    MODULES = (
        "viur.core.prototypes.list", "viur.core.prototypes.tree", "viur.core.prototypes.singleton",
        "viur.core.prototypes.skelmodule", "viur.core.modules.user", "viur.core.modules.file",
        "viur.core.modules.translation", "viur.core.modules.script", "viur.core.modules.formmailer",
        "viur.core.modules.site", "viur.core.modules.page", "viur.core.modules.moduleconf",
        "viur.core.modules.history", "viur.core.modules.email", "viur.core.tasks",
    )

    def _actions(self):
        import importlib
        import inspect
        from viur.core import Module

        for module_name in self.MODULES:
            module = importlib.import_module(module_name)
            for name, cls in vars(module).items():
                if inspect.isclass(cls) and issubclass(cls, Module) and cls.__module__ == module_name:
                    for action, method in cls._actions.items():
                        yield f"{module_name}.{name}.{action}", cls, action, method

    def test_no_action_relies_on_the_fail_closed_fallback(self):
        from viur.core import Module
        from viur.core.actions import resolve_hook_names
        from viur.core.module import _HOOK_ALIAS

        for path, cls, action, _ in self._actions():
            with self.subTest(action=path):
                hook = getattr(cls, resolve_hook_names(action)[0])
                self.assertFalse(
                    getattr(hook, _HOOK_ALIAS, False) and cls.can is Module.can,
                    f"{path} has no {resolve_hook_names(action)[0]}",
                )

    def test_every_action_calls_its_can_hook_or_delegates_to_super(self):
        import inspect
        from viur.core.actions import resolve_hook_names

        for path, cls, action, method in self._actions():
            with self.subTest(action=path):
                source = inspect.getsource(method._func)
                self.assertTrue(
                    f"self.{resolve_hook_names(action)[0]}(" in source or f"super().{action}(" in source,
                    f"{path} does not call {resolve_hook_names(action)[0]}",
                )


class TestContext(ViURTestCase):
    """A client names its contexts by header; a context counts only for users with a right it requires."""

    def _module(self, headers=None, user=None):
        from unittest import mock
        from viur.core import Module, current

        self.response = mock.Mock(vary=None)
        current.request.set(mock.Mock(request=mock.Mock(headers=headers or {}), response=self.response))
        current.user.set(user)
        return Module("article", "/json/article")

    def test_without_the_header_there_is_no_context(self):
        self.assertFalse(self._module(user={"access": ["root"]}).has_context("admin"))

    def test_the_header_alone_grants_nothing(self):
        self.assertFalse(self._module({"X-VIUR-CONTEXT": "admin"}).has_context("admin"))

    def test_admin_needs_admin_or_root(self):
        headers = {"X-VIUR-CONTEXT": "admin"}
        self.assertFalse(self._module(headers, {"access": ["article-view"]}).has_context("admin"))
        self.assertTrue(self._module(headers, {"access": ["admin"]}).has_context("admin"))
        self.assertTrue(self._module(headers, {"access": ["root"]}).has_context("admin"))

    def test_the_header_value_is_case_insensitive(self):
        self.assertTrue(self._module({"X-VIUR-CONTEXT": "Admin"}, {"access": ["root"]}).has_context("admin"))

    def test_a_project_context_uses_its_configured_rights(self):
        from viur.core import conf
        self.addCleanup(conf.security.contexts.pop, "partner")
        conf.security.contexts["partner"] = ("partner-portal",)

        module = self._module({"X-VIUR-CONTEXT": "admin, partner"}, {"access": ["partner-portal"]})
        self.assertTrue(module.has_context("partner"))
        self.assertFalse(module.has_context("admin"))

    def test_a_context_that_is_not_configured_is_never_granted(self):
        self.assertFalse(self._module({"X-VIUR-CONTEXT": "unknown"}, {"access": ["root"]}).has_context("unknown"))

    def test_the_response_varies_on_the_header_once(self):
        module = self._module()
        module.has_context("admin")
        module.has_context("admin")
        self.assertEqual(("X-VIUR-CONTEXT",), self.response.vary)

    def test_outside_a_request_there_is_no_context(self):
        from viur.core import Module, current
        current.request.set(None)
        self.assertFalse(Module("article", "/json/article").has_context("admin"))

    def test_the_header_is_allowed_for_cross_origin_requests_by_default(self):
        from viur.core.config import Security
        from viur.core.module import X_VIUR_CONTEXT
        self.assertIn(X_VIUR_CONTEXT, Security.cors_allow_headers)
