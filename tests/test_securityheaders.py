"""Tests for the reporting parts of :class:`viur.core.config.Security`.

Anything from :mod:`viur.core` is imported inside the test methods, not at module level:
:meth:`ViURTestCase.setUp` has to mock ``google.auth.default`` first, because
:mod:`viur.core.config` resolves the project id while it is being imported.
"""
import copy
from unittest import mock

from abstract import ViURTestCase


class TestReportingEndpoints(ViURTestCase):
    def setUp(self) -> None:
        super().setUp()
        from viur.core.config import conf
        self.endpoints_backup = copy.deepcopy(conf.security.reporting_endpoints)
        conf.security.reporting_endpoints.clear()

    def tearDown(self) -> None:
        from viur.core.config import conf
        conf.security.reporting_endpoints.clear()
        conf.security.reporting_endpoints.update(self.endpoints_backup)
        super().tearDown()

    def test_set_relative_url(self):
        from viur.core.config import conf
        conf.security.set_reporting_endpoint("csp", "/cspReport")
        self.assertEqual({"csp": "/cspReport"}, conf.security.reporting_endpoints)

    def test_set_absolute_url(self):
        from viur.core.config import conf
        conf.security.set_reporting_endpoint("default", "https://example.com/reports")
        self.assertEqual({"default": "https://example.com/reports"}, conf.security.reporting_endpoints)

    def test_overwrite_url(self):
        from viur.core.config import conf
        conf.security.set_reporting_endpoint("csp", "/old")
        conf.security.set_reporting_endpoint("csp", "/new")
        self.assertEqual({"csp": "/new"}, conf.security.reporting_endpoints)

    def test_remove_endpoint(self):
        from viur.core.config import conf
        conf.security.set_reporting_endpoint("csp", "/cspReport")
        conf.security.set_reporting_endpoint("csp", None)
        self.assertEqual({}, conf.security.reporting_endpoints)

    def test_remove_unknown_endpoint(self):
        from viur.core.config import conf
        conf.security.set_reporting_endpoint("csp", None)  # must not raise
        self.assertEqual({}, conf.security.reporting_endpoints)

    def test_valid_names(self):
        from viur.core.config import conf
        for name in ("csp", "default", "my-endpoint", "e2", "a.b_c*", "*all"):
            with self.subTest(name=name):
                conf.security.set_reporting_endpoint(name, "/report")
                self.assertIn(name, conf.security.reporting_endpoints)

    def test_invalid_names(self):
        from viur.core.config import conf
        for name in ("", "CSP", "1csp", "-csp", ".csp", "csp endpoint", "csp,other", 'csp"'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    conf.security.set_reporting_endpoint(name, "/report")
        self.assertEqual({}, conf.security.reporting_endpoints)

    def test_invalid_urls(self):
        from viur.core.config import conf
        for url in ("", "http://example.com/reports", "https://example.com/a b", 'https://example.com/"',
                    "https://example.com/a,b", "https://example.com/a;b", "https://example.com/a\nb"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    conf.security.set_reporting_endpoint("csp", url)
        self.assertEqual({}, conf.security.reporting_endpoints)

    def test_header_is_empty_without_endpoints(self):
        from viur.core.config import conf
        self.assertEqual("", conf.security._build_reporting_endpoints_header())

    def test_header_value(self):
        from viur.core.config import conf
        conf.security.set_reporting_endpoint("csp", "/cspReport")
        conf.security.set_reporting_endpoint("default", "https://example.com/reports")
        self.assertEqual(
            'csp="/cspReport", default="https://example.com/reports"',
            conf.security._build_reporting_endpoints_header(),
        )


class TestCspReportingDirectives(ViURTestCase):
    def setUp(self) -> None:
        super().setUp()
        from viur.core.config import conf
        self.csp_backup = copy.deepcopy(conf.security.content_security_policy)
        # addCspRule refuses to run once the app has been built, which other tests in this suite may have done
        self.main_app_backup = conf.main_app
        conf.main_app = None

    def tearDown(self) -> None:
        from viur.core.config import conf
        conf.security.content_security_policy = self.csp_backup
        conf.security._build_csp_header_cache()
        conf.main_app = self.main_app_backup
        super().tearDown()

    def test_report_to_holds_a_single_token(self):
        from viur.core.config import conf
        conf.security.add_csp_rule("report-to", "old-endpoint", "enforce")
        conf.security.add_csp_rule("report-to", "csp", "enforce")
        self.assertEqual(["csp"], conf.security.content_security_policy["enforce"]["report-to"])

    def test_report_uri_holds_a_single_url(self):
        from viur.core.config import conf
        conf.security.add_csp_rule("report-uri", "/old", "enforce")
        conf.security.add_csp_rule("report-uri", "/cspReport", "enforce")
        self.assertEqual(["/cspReport"], conf.security.content_security_policy["enforce"]["report-uri"])

    def test_report_to_without_endpoint_warns(self):
        from viur.core.config import conf
        conf.security.add_csp_rule("report-to", "unknown", "enforce")
        with self.assertLogs(level="WARNING") as logs:
            conf.security._validate_reporting_config()
        self.assertIn("'unknown'", "".join(logs.output))

    def test_report_to_with_endpoint_is_silent(self):
        from viur.core.config import conf
        conf.security.set_reporting_endpoint("csp", "/cspReport")
        self.addCleanup(conf.security.set_reporting_endpoint, "csp", None)
        conf.security.add_csp_rule("report-to", "csp", "enforce")
        with self.assertNoLogs(level="WARNING"):
            conf.security._validate_reporting_config()

    def test_dev_server_warns_about_http_endpoints(self):
        from viur.core.config import conf
        conf.security.set_reporting_endpoint("csp", "/cspReport")
        self.addCleanup(conf.security.set_reporting_endpoint, "csp", None)
        conf.security.add_csp_rule("report-to", "csp", "enforce")
        with mock.patch.object(type(conf.instance), "is_dev_server", True):
            with self.assertLogs(level="WARNING") as logs:
                conf.security._validate_reporting_config()
        self.assertIn("https", "".join(logs.output))

    def test_reporting_directives_are_not_quoted(self):
        from viur.core.config import conf
        conf.security.add_csp_rule("report-to", "csp", "enforce")
        conf.security.add_csp_rule("report-uri", "/cspReport", "enforce")
        conf.security._build_csp_header_cache()
        header = conf.security._csp_header_cache["Content-Security-Policy"]
        self.assertIn("report-to csp; ", header)
        self.assertIn("report-uri /cspReport; ", header)


class TestExtendCsp(ViURTestCase):
    """``conf.security.content_security_policy`` is optional and may be None.

    The error page calls :func:`extendCsp` for its style nonce, so a crash here turns an
    error response into a second error.
    """

    def setUp(self) -> None:
        super().setUp()
        from viur.core import current
        from viur.core.config import conf
        self.csp_backup = copy.deepcopy(conf.security.content_security_policy)
        request = mock.MagicMock()
        request.response.headers = {}
        self.request = request
        token = current.request.set(request)
        self.addCleanup(current.request.reset, token)

    def tearDown(self) -> None:
        from viur.core.config import conf
        conf.security.content_security_policy = self.csp_backup
        super().tearDown()

    def _header(self) -> str:
        return self.request.response.headers["Content-Security-Policy"]

    def test_without_project_policy(self):
        from viur.core.config import conf
        conf.security.content_security_policy = None
        conf.security.extend_csp({"style-src": ["nonce-abc"]})
        self.assertEqual("style-src 'nonce-abc'; ", self._header())

    def test_project_policy_is_extended(self):
        from viur.core.config import conf
        conf.security.content_security_policy = {"enforce": {"style-src": ["self"]}}
        conf.security.extend_csp({"style-src": ["nonce-abc"]})
        self.assertEqual("style-src 'self' 'nonce-abc'; ", self._header())

    def test_project_policy_is_not_mutated(self):
        from viur.core.config import conf
        conf.security.content_security_policy = {"enforce": {"style-src": ["self"]}}
        conf.security.extend_csp({"style-src": ["nonce-abc"]})
        self.assertEqual({"enforce": {"style-src": ["self"]}}, conf.security.content_security_policy)
