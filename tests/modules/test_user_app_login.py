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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_self():
    """Bare User instance (no __init__) — the tested methods don't use instance state."""
    from viur.core.modules.user import User
    return object.__new__(User)


def _mock_user(db_entity, access=("root",)):
    _data = {"key": db_entity.key, "access": list(access)}
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
        conf.user.app_login_access = None
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

    def test_wildcard_does_not_reach_into_query(self):
        from viur.core import conf, errors
        from viur.core.modules.user import User

        conf.user.redirect_whitelist = ["https://*-dot-myapp.appspot.com"]
        with self.assertRaises(errors.Forbidden):
            User.get_cookie_for_app(
                _user_self(),
                redirect_to="https://evil.example/?x=v1-dot-myapp.appspot.com",
            )


# ---------------------------------------------------------------------------
# get_cookie_for_app – access check (conf.user.app_login_access)
# ---------------------------------------------------------------------------

class TestGetCookieAccess(AppLoginTestCase):
    """get_cookie_for_app: who may use the App Login Flow."""

    def _login_as(self, *access):
        from viur.core import current, db

        current.user.set(_mock_user(db.Entity(self.user_key), access))

    def _assert_allowed(self):
        from viur.core.modules.user import User

        self.assertIn("=", User.get_cookie_for_app(_user_self()))

    def _assert_forbidden(self):
        from viur.core import errors
        from viur.core.modules.user import User

        with self.assertRaises(errors.Forbidden):
            User.get_cookie_for_app(_user_self())

    def test_default_allows_every_authenticated_user(self):
        self._login_as()
        self._assert_allowed()

    def test_not_logged_in_is_redirected_to_login(self):
        from viur.core import current, errors
        from viur.core.modules.user import User

        current.user.set(None)
        with self.assertRaises(errors.Redirect):
            User.get_cookie_for_app(_user_self())

    def test_restricted_to_admin(self):
        from viur.core import conf

        conf.user.app_login_access = ("admin",)
        for access, allowed in ((["user-view"], False), (["admin"], True), (["root"], True)):
            with self.subTest(access=access):
                self._login_as(*access)
                if allowed:
                    self._assert_allowed()
                else:
                    self._assert_forbidden()

    def test_combined_rights_are_all_required(self):
        from viur.core import conf

        conf.user.app_login_access = [["admin", "user-edit"]]
        self._login_as("admin")
        self._assert_forbidden()
        self._login_as("admin", "user-edit")
        self._assert_allowed()


# ---------------------------------------------------------------------------
# _is_redirect_allowed
# ---------------------------------------------------------------------------

class TestIsRedirectAllowed(ViURTestCase):
    """_is_redirect_allowed: scheme, host, port and path are matched separately."""

    def _check(self, whitelist, cases):
        from viur.core.modules.user import _is_redirect_allowed

        for url, expected in cases:
            with self.subTest(url=url):
                self.assertIs(_is_redirect_allowed(url, whitelist), expected)

    def test_default_whitelist(self):
        self._check(
            [
                "http://localhost:*",
                "https://myapp.appspot.com",
                "https://*-dot-myapp.appspot.com",
            ],
            [
                ("http://localhost:60000", True),
                ("http://localhost:60000/?state=abc", True),
                ("https://myapp.appspot.com/cb", True),
                ("https://v1-dot-myapp.appspot.com/cb", True),
                ("https://MYAPP.appspot.com/cb", True),
                ("http://localhost", False),  # pattern requires a port
                ("https://localhost:60000", False),  # scheme mismatch
                ("https://myapp.appspot.com:8443/cb", False),  # unexpected port
                ("https://evil.example/?x=myapp.appspot.com", False),
                ("https://evil.example/myapp.appspot.com", False),
                ("https://myapp.appspot.com.evil.example/cb", False),
                ("https://evilmyapp.appspot.com/cb", False),
                ("http://localhost:60000@evil.example/", False),
                ("http://user@localhost:60000/", False),
                ("https://evil.example\\x-dot-myapp.appspot.com/", False),
                ("javascript://localhost:1/%0aalert(1)", False),
                ("//localhost:60000/", False),
                ("http://localhost:abc/", False),
            ],
        )

    def test_path_pattern(self):
        self._check(
            ["https://tools.example.com/callback/*"],
            [
                ("https://tools.example.com/callback/login", True),
                ("https://tools.example.com/other", False),
                ("https://tools.example.com", False),
            ],
        )

    def test_ipv6_host_is_rejected(self):
        self._check(["*://*", "http://*:*"], [("http://[::1]:60000/", False)])

    def test_star_and_invalid_patterns(self):
        self._check(["*"], [("https://anything.example/x", True)])
        self._check(["localhost:*", ""], [("http://localhost:1/", False)])


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
