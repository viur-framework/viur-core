"""
Tests for the App Login Flow:
  User._get_cookie_for_app – session creation in Datastore, Set-Cookie format
  User.get_cookie_for_app  – whitelist check, redirect or plain-text response
  User.apply_login_cookie  – session activation from a Set-Cookie string
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from abstract import ViURTestCase  # noqa: E402


def _ensure_skeleton_search_path():
    """Add the in-tree /src/viur/core/ path so MetaSkel's path check passes when
    running tests directly from the viur-core checkout (not an installed package)."""
    from viur.core import conf
    if "/src/viur/core/" not in conf.skeleton_search_path:
        conf.skeleton_search_path = list(conf.skeleton_search_path) + ["/src/viur/core/"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_self():
    """Bare User instance (no __init__) — the tested methods don't use instance state."""
    from viur.core.modules.user import User
    return object.__new__(User)


def _mock_user(db_entity):
    _data = {"key": db_entity.key, "access": ["root"]}
    user = mock.MagicMock()
    user.dbEntity = db_entity
    user.__getitem__ = mock.Mock(side_effect=lambda k: _data.get(k, db_entity.get(k)))
    return user


def _setup_request_context():
    """Wire current.request with a real cookies dict; return (mock_req, cookies_dict)."""
    from viur.core import current
    cookies = {}
    req = mock.MagicMock()
    req.request = mock.MagicMock()
    req.request.cookies = cookies
    req.response = mock.MagicMock()
    req.response.headers = {}
    current.request.set(req)
    return req, cookies


class FakeDatastore:
    """Tiny in-memory substitute for db.put / db.get."""

    def __init__(self):
        self._store: dict = {}

    def put(self, entity):
        self._store[entity.key] = entity

    def get(self, key):
        return self._store.get(key)


# ---------------------------------------------------------------------------
# Base class with shared wiring
# ---------------------------------------------------------------------------

class AppLoginTestCase(ViURTestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_skeleton_search_path()

    def setUp(self):
        super().setUp()
        from viur.core import current, db

        self.fake_db = FakeDatastore()
        self._patch_put = mock.patch("viur.core.db.put", side_effect=self.fake_db.put)
        self._patch_get = mock.patch("viur.core.db.get", side_effect=self.fake_db.get)
        self._patch_put.start()
        self._patch_get.start()

        # User entity (in-memory only; never written to real Datastore)
        self.user_key = db.Key("user", "test-user")
        user_entity = db.Entity(self.user_key)
        user_entity["name"] = "Test"
        current.user.set(_mock_user(user_entity))

        self.mock_req, self.cookies = _setup_request_context()

    def tearDown(self):
        self._patch_put.stop()
        self._patch_get.stop()
        from viur.core import conf
        conf.user.redirect_whitelist = None
        super().tearDown()


# ---------------------------------------------------------------------------
# _get_cookie_for_app
# ---------------------------------------------------------------------------

class TestPrivateGetCookie(AppLoginTestCase):
    """_get_cookie_for_app: session creation and return-value format."""

    def test_returns_set_cookie_string(self):
        from viur.core.modules.user import User
        from viur.core.session import Session

        result = User._get_cookie_for_app(_user_self())

        self.assertIsInstance(result, str)
        self.assertTrue(
            result.startswith(Session.cookie_name + "="),
            f"Expected prefix '{Session.cookie_name}=', got: {result!r}",
        )

    def test_persists_session_in_datastore(self):
        from viur.core.modules.user import User
        from viur.core.session import Session
        from viur.core import db

        result = User._get_cookie_for_app(_user_self())
        session_key_str = result.split(";")[0].split("=", 1)[1]

        entity = self.fake_db.get(db.Key(Session.kindName, session_key_str))
        self.assertIsNotNone(entity, "Session entity missing from Datastore")

    def test_session_entity_fields(self):
        from viur.core.modules.user import User
        from viur.core.session import Session
        from viur.core import db

        result = User._get_cookie_for_app(_user_self())
        session_key_str = result.split(";")[0].split("=", 1)[1]
        entity = self.fake_db.get(db.Key(Session.kindName, session_key_str))

        self.assertTrue(entity["data"]["is_app_session"])
        self.assertIn("static_security_key", entity)
        self.assertIn("lastseen", entity)
        self.assertEqual(entity["user"], str(self.user_key))


# ---------------------------------------------------------------------------
# get_cookie_for_app – no redirect
# ---------------------------------------------------------------------------

class TestGetCookieNoRedirect(AppLoginTestCase):
    """get_cookie_for_app without redirect_to: plain-text response."""

    def test_sets_content_type_text_plain(self):
        from viur.core.modules.user import User

        User.get_cookie_for_app(_user_self())

        self.assertEqual(self.mock_req.response.headers.get("Content-Type"), "text/plain")

    def test_returns_cookie_string(self):
        from viur.core.modules.user import User
        from viur.core.session import Session

        result = User.get_cookie_for_app(_user_self())

        self.assertTrue(result.startswith(Session.cookie_name + "="))


# ---------------------------------------------------------------------------
# get_cookie_for_app – whitelist / redirect
# ---------------------------------------------------------------------------

class TestGetCookieWhitelist(AppLoginTestCase):
    """get_cookie_for_app: whitelist enforcement and redirect behaviour."""

    def setUp(self):
        super().setUp()
        from viur.core import conf
        conf.user.redirect_whitelist = ["http://localhost:*"]

    # --- allowed ---

    def test_whitelisted_url_raises_redirect(self):
        from viur.core.modules.user import User
        from viur.core import errors

        with self.assertRaises(errors.Redirect):
            User.get_cookie_for_app(_user_self(), redirect_to="http://localhost:8080")

    def test_redirect_url_contains_cookie_and_app_params(self):
        from viur.core.modules.user import User
        from viur.core import errors

        with self.assertRaises(errors.Redirect) as ctx:
            User.get_cookie_for_app(_user_self(), redirect_to="http://localhost:8080")

        self.assertIn("cookie=", ctx.exception.url)
        self.assertIn("app=", ctx.exception.url)

    def test_question_mark_appended_when_missing(self):
        from viur.core.modules.user import User
        from viur.core import errors

        with self.assertRaises(errors.Redirect) as ctx:
            User.get_cookie_for_app(_user_self(), redirect_to="http://localhost:8080/cb")

        self.assertIn("?", ctx.exception.url)

    def test_question_mark_not_doubled(self):
        from viur.core.modules.user import User
        from viur.core import errors

        with self.assertRaises(errors.Redirect) as ctx:
            User.get_cookie_for_app(_user_self(), redirect_to="http://localhost:8080/cb?x=1")

        self.assertEqual(ctx.exception.url.count("?"), 1)

    # --- blocked ---

    def test_non_whitelisted_raises_forbidden(self):
        from viur.core.modules.user import User
        from viur.core import errors

        with self.assertRaises(errors.Forbidden):
            User.get_cookie_for_app(_user_self(), redirect_to="https://evil.com/steal")

    def test_empty_whitelist_blocks_all(self):
        from viur.core import conf, errors
        from viur.core.modules.user import User

        conf.user.redirect_whitelist = []
        with self.assertRaises(errors.Forbidden):
            User.get_cookie_for_app(_user_self(), redirect_to="http://localhost:8080")

    # --- whitelist variants ---

    def test_star_allows_any_url(self):
        from viur.core import conf, errors
        from viur.core.modules.user import User

        conf.user.redirect_whitelist = ["*"]
        with self.assertRaises(errors.Redirect):
            User.get_cookie_for_app(_user_self(), redirect_to="https://evil.com/steal")

    def test_callable_whitelist_is_evaluated(self):
        from viur.core import conf, errors
        from viur.core.modules.user import User

        conf.user.redirect_whitelist = lambda: ["http://localhost:*"]
        with self.assertRaises(errors.Redirect):
            User.get_cookie_for_app(_user_self(), redirect_to="http://localhost:9000")

    def test_callable_whitelist_can_block(self):
        from viur.core import conf, errors
        from viur.core.modules.user import User

        conf.user.redirect_whitelist = lambda: ["http://localhost:*"]
        with self.assertRaises(errors.Forbidden):
            User.get_cookie_for_app(_user_self(), redirect_to="https://evil.com")

    def test_fnmatch_pattern(self):
        from viur.core import conf, errors
        from viur.core.modules.user import User

        conf.user.redirect_whitelist = ["https://*.myapp.appspot.com*"]
        with self.assertRaises(errors.Redirect):
            User.get_cookie_for_app(
                _user_self(),
                redirect_to="https://v1.myapp.appspot.com/apply_login_cookie",
            )


# ---------------------------------------------------------------------------
# apply_login_cookie
# ---------------------------------------------------------------------------

class TestApplyLoginCookie(AppLoginTestCase):
    """apply_login_cookie: session activation from a Set-Cookie string."""

    def setUp(self):
        super().setUp()
        from viur.core import current, conf

        conf.user.redirect_whitelist = ["*"]

        self.mock_session = mock.MagicMock()
        current.session.set(self.mock_session)

    def _valid_cookie(self):
        from viur.core.modules.user import User
        return User._get_cookie_for_app(_user_self())

    def test_raises_redirect_to_root(self):
        from viur.core.modules.user import User
        from viur.core import errors

        with self.assertRaises(errors.Redirect) as ctx:
            User.apply_login_cookie(_user_self(), cookie=self._valid_cookie())

        self.assertEqual(ctx.exception.url, "/")

    def test_resets_session(self):
        from viur.core.modules.user import User
        from viur.core import errors

        try:
            User.apply_login_cookie(_user_self(), cookie=self._valid_cookie())
        except errors.Redirect:
            pass

        self.mock_session.reset.assert_called_once()

    def test_injects_cookie_into_request(self):
        from viur.core.modules.user import User
        from viur.core.session import Session
        from viur.core import errors

        try:
            User.apply_login_cookie(_user_self(), cookie=self._valid_cookie())
        except errors.Redirect:
            pass

        self.assertIn(Session.cookie_name, self.cookies)

    def test_loads_session(self):
        from viur.core.modules.user import User
        from viur.core import errors

        try:
            User.apply_login_cookie(_user_self(), cookie=self._valid_cookie())
        except errors.Redirect:
            pass

        self.mock_session.load.assert_called_once()

    def test_wrong_cookie_name_raises_bad_request(self):
        from viur.core.modules.user import User
        from viur.core import errors

        with self.assertRaises(errors.BadRequest):
            User.apply_login_cookie(_user_self(), cookie="wrong_name=abc123;Path=/")

    def test_empty_cookie_raises_bad_request(self):
        from viur.core.modules.user import User
        from viur.core import errors

        with self.assertRaises(errors.BadRequest):
            User.apply_login_cookie(_user_self(), cookie="")


if __name__ == "__main__":
    unittest.main()
