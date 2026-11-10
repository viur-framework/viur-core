"""Tests for the error rendering of :class:`viur.core.request.Router`.

The router is driven through a real WSGI environ; only the session (which would hit the
datastore) and the main app are replaced by stand-ins.

Anything from :mod:`viur.core` is imported inside the test methods, not at module level:
:meth:`ViURTestCase.setUp` has to mock ``google.auth.default`` first, because
:mod:`viur.core.config` resolves the project id while it is being imported.
"""
import json
import types
from unittest import mock

import webob

from abstract import ViURTestCase


class TestRouterErrorFormat(ViURTestCase):
    def setUp(self) -> None:
        super().setUp()
        from viur.core.config import conf

        self.conf_backup = {
            "closed_system": conf.security.closed_system,
            "request_preprocessor": conf.request_preprocessor,
            "main_app": conf.main_app,
            "main_resolver": conf.main_resolver,
        }

        # An app without a user module and without error templates, so nothing reaches out
        # to the datastore and the HTML branch falls back to its inline page.
        conf.main_app = types.SimpleNamespace(
            vi=types.SimpleNamespace(),
            render=types.SimpleNamespace(getTemplateFileName=lambda *args, **kwargs: None),
        )
        conf.main_resolver = {}
        conf.request_preprocessor = None

        session_patcher = mock.patch("viur.core.request.session.Session")
        session_patcher.start()
        self.addCleanup(session_patcher.stop)

        # The CSP header cache is only built by viur.core.setup(), which these tests skip.
        csp_patcher = mock.patch.object(conf.security, "content_security_policy", {})
        csp_patcher.start()
        self.addCleanup(csp_patcher.stop)

    def tearDown(self) -> None:
        from viur.core.config import conf
        conf.security.closed_system = self.conf_backup["closed_system"]
        conf.request_preprocessor = self.conf_backup["request_preprocessor"]
        conf.main_app = self.conf_backup["main_app"]
        conf.main_resolver = self.conf_backup["main_resolver"]
        super().tearDown()

    @staticmethod
    def _request(path: str) -> webob.Response:
        from viur.core.request import Router
        return Router(webob.Request.blank(path, base_url="https://localhost").environ).response

    def assertJsonError(self, response: webob.Response, status: int) -> None:
        self.assertEqual(status, response.status_code)
        self.assertEqual("application/json", response.content_type)
        self.assertEqual(status, json.loads(response.body)["status"])

    def assertHtmlError(self, response: webob.Response, status: int) -> None:
        self.assertEqual(status, response.status_code)
        self.assertNotEqual("application/json", response.content_type)
        self.assertTrue(response.body.startswith(b"<!DOCTYPE html>"))

    def test_closed_system_json_path(self):
        from viur.core.config import conf
        conf.security.closed_system = True
        response = self._request("/json/user/view/self")
        self.assertJsonError(response, 401)
        self.assertEqual("The resource is protected and you don't have the permissions.",
                         response.headers["x-viur-error"])

    def test_closed_system_vi_path(self):
        from viur.core.config import conf
        conf.security.closed_system = True
        self.assertJsonError(self._request("/vi/user/view/self"), 401)

    def test_closed_system_html_path(self):
        from viur.core.config import conf
        conf.security.closed_system = True
        self.assertHtmlError(self._request("/user/view/self"), 401)

    def test_request_preprocessor_raises_on_json_path(self):
        from viur.core import errors
        from viur.core.config import conf

        def preprocessor(path: str) -> str:
            raise errors.Forbidden()

        conf.request_preprocessor = preprocessor
        self.assertJsonError(self._request("/json/user/view/self"), 403)

    def test_request_preprocessor_rewrites_into_json_path(self):
        from viur.core.config import conf
        conf.request_preprocessor = lambda path: path.replace("api/", "json/", 1)
        self.assertJsonError(self._request("/api/unknown"), 404)

    def test_request_preprocessor_rewrites_out_of_json_path(self):
        from viur.core.config import conf
        conf.request_preprocessor = lambda path: path.replace("json/", "", 1)
        self.assertHtmlError(self._request("/json/unknown"), 404)
