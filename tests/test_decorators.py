"""
Tests for viur.core.decorators:
  exposed, internal_exposed, force_ssl, force_post, access, cors
"""
from unittest import mock

from abstract import ViURTestCase


def _set_user(access_rights: list[str] | None):
    """Set current.user to a mock with the given access list, or None for no user."""
    from viur.core import current
    if access_rights is None:
        current.user.set(None)
        return
    user = mock.MagicMock()
    user.__getitem__ = mock.Mock(side_effect=lambda k: access_rights if k == "access" else None)
    current.user.set(user)


class TestExposedDecorator(ViURTestCase):

    def test_marks_function_exposed(self):
        from viur.core.decorators import exposed

        @exposed
        def my_func():
            return "ok"

        self.assertTrue(my_func.exposed)

    def test_with_seo_map(self):
        from viur.core.decorators import exposed

        @exposed({"de": "meine-funktion"})
        def my_func():
            return "ok"

        self.assertTrue(my_func.exposed)
        self.assertEqual({"de": "meine-funktion"}, my_func.seo_language_map)


class TestInternalExposedDecorator(ViURTestCase):

    def test_marks_function_not_exposed(self):
        from viur.core.decorators import internal_exposed

        @internal_exposed
        def my_func():
            return "ok"

        self.assertFalse(my_func.exposed)


class TestForcePostDecorator(ViURTestCase):

    def test_sets_post_method(self):
        from viur.core.decorators import force_post

        @force_post
        def my_func():
            return "ok"

        self.assertIn("POST", my_func.methods)
        self.assertNotIn("GET", my_func.methods)


class TestForceSslDecorator(ViURTestCase):

    def test_sets_ssl_flag(self):
        from viur.core.decorators import force_ssl

        @force_ssl
        def my_func():
            return "ok"

        self.assertTrue(my_func.ssl)


class TestCorsDecorator(ViURTestCase):

    def test_sets_cors_headers(self):
        from viur.core.decorators import cors, exposed

        @exposed
        @cors(allow_headers=["X-Custom-Header"])
        def my_func():
            return "ok"

        self.assertIn("X-Custom-Header", my_func.cors_allow_headers)


# ---------------------------------------------------------------------------
# @access decorator
# ---------------------------------------------------------------------------

class TestAccessDecorator(ViURTestCase):

    def setUp(self):
        super().setUp()
        # set up a minimal request context for current.user
        from viur.core import current
        req = mock.MagicMock()
        req.request = mock.MagicMock()
        current.request.set(req)

    def _call(self, func):
        """Invoke a Method's guards then the function."""
        from viur.core.module import Method
        # call the guards manually (Method.__call__ runs them)
        for guard in func.guards:
            guard()

    # --- no user ---

    def test_no_user_raises_unauthorized(self):
        from viur.core.decorators import access
        from viur.core import errors

        _set_user(None)

        @access("admin")
        def fn():
            return "ok"

        with self.assertRaises(errors.Unauthorized):
            self._call(fn)

    def test_no_user_offer_login_redirects(self):
        from viur.core.decorators import access
        from viur.core import errors

        _set_user(None)

        @access("admin", offer_login=True)
        def fn():
            return "ok"

        with self.assertRaises(errors.Redirect) as ctx:
            self._call(fn)

        self.assertEqual("/user/login", ctx.exception.url)

    def test_no_user_offer_login_custom_url(self):
        from viur.core.decorators import access
        from viur.core import errors

        _set_user(None)

        @access("admin", offer_login="/auth/login")
        def fn():
            return "ok"

        with self.assertRaises(errors.Redirect) as ctx:
            self._call(fn)

        self.assertEqual("/auth/login", ctx.exception.url)

    # --- root user bypasses all checks ---

    def test_root_access_always_allowed(self):
        from viur.core.decorators import access

        _set_user(["root"])

        @access("admin")
        def fn():
            return "ok"

        self._call(fn)  # must not raise

    # --- specific access rights ---

    def test_user_with_required_access(self):
        from viur.core.decorators import access

        _set_user(["admin"])

        @access("admin")
        def fn():
            return "ok"

        self._call(fn)  # must not raise

    def test_user_without_required_access_raises_forbidden(self):
        from viur.core.decorators import access
        from viur.core import errors

        _set_user(["editor"])

        @access("admin")
        def fn():
            return "ok"

        with self.assertRaises(errors.Forbidden):
            self._call(fn)

    def test_any_of_multiple_access_rights(self):
        from viur.core.decorators import access

        _set_user(["editor"])

        @access("admin", "editor")
        def fn():
            return "ok"

        self._call(fn)  # must not raise

    def test_combined_access_all_required(self):
        from viur.core.decorators import access
        from viur.core import errors

        # requires BOTH admin AND file-edit
        _set_user(["admin"])  # only admin, missing file-edit

        @access(["admin", "file-edit"])
        def fn():
            return "ok"

        with self.assertRaises(errors.Forbidden):
            self._call(fn)

    def test_combined_access_all_present(self):
        from viur.core.decorators import access

        _set_user(["admin", "file-edit"])

        @access(["admin", "file-edit"])
        def fn():
            return "ok"

        self._call(fn)  # must not raise

    def test_callable_access_grant(self):
        from viur.core.decorators import access

        _set_user([])  # no specific rights

        @access(lambda: True)
        def fn():
            return "ok"

        self._call(fn)  # callable returns True → access granted

    def test_callable_access_deny(self):
        from viur.core.decorators import access
        from viur.core import errors

        _set_user([])

        @access(lambda: False)
        def fn():
            return "ok"

        with self.assertRaises(errors.Forbidden):
            self._call(fn)

    def test_custom_message_in_forbidden(self):
        from viur.core.decorators import access
        from viur.core import errors

        _set_user(["editor"])

        @access("admin", message="Nope")
        def fn():
            return "ok"

        with self.assertRaises(errors.Forbidden) as ctx:
            self._call(fn)

        self.assertIn("Nope", ctx.exception.descr)
