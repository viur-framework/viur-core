"""Tests for the reporting parts of :mod:`viur.core.securityheaders`."""
import copy
from unittest import mock

from abstract import ViURTestCase

from viur.core import securityheaders
from viur.core.config import conf


class TestReportingEndpoints(ViURTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.endpoints_backup = copy.deepcopy(conf.security.reporting_endpoints)
        conf.security.reporting_endpoints.clear()

    def tearDown(self) -> None:
        conf.security.reporting_endpoints.clear()
        conf.security.reporting_endpoints.update(self.endpoints_backup)
        super().tearDown()

    def test_set_relative_url(self):
        securityheaders.set_reporting_endpoint("csp", "/cspReport")
        self.assertEqual({"csp": "/cspReport"}, conf.security.reporting_endpoints)

    def test_set_absolute_url(self):
        securityheaders.set_reporting_endpoint("default", "https://example.com/reports")
        self.assertEqual({"default": "https://example.com/reports"}, conf.security.reporting_endpoints)

    def test_overwrite_url(self):
        securityheaders.set_reporting_endpoint("csp", "/old")
        securityheaders.set_reporting_endpoint("csp", "/new")
        self.assertEqual({"csp": "/new"}, conf.security.reporting_endpoints)

    def test_remove_endpoint(self):
        securityheaders.set_reporting_endpoint("csp", "/cspReport")
        securityheaders.set_reporting_endpoint("csp", None)
        self.assertEqual({}, conf.security.reporting_endpoints)

    def test_remove_unknown_endpoint(self):
        securityheaders.set_reporting_endpoint("csp", None)  # must not raise
        self.assertEqual({}, conf.security.reporting_endpoints)

    def test_valid_names(self):
        for name in ("csp", "default", "my-endpoint", "e2", "a.b_c*", "*all"):
            with self.subTest(name=name):
                securityheaders.set_reporting_endpoint(name, "/report")
                self.assertIn(name, conf.security.reporting_endpoints)

    def test_invalid_names(self):
        for name in ("", "CSP", "1csp", "-csp", ".csp", "csp endpoint", "csp,other", 'csp"'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    securityheaders.set_reporting_endpoint(name, "/report")
        self.assertEqual({}, conf.security.reporting_endpoints)

    def test_invalid_urls(self):
        for url in ("", "http://example.com/reports", "https://example.com/a b", 'https://example.com/"',
                    "https://example.com/a,b", "https://example.com/a;b", "https://example.com/a\nb"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    securityheaders.set_reporting_endpoint("csp", url)
        self.assertEqual({}, conf.security.reporting_endpoints)

    def test_header_is_empty_without_endpoints(self):
        self.assertEqual("", securityheaders._build_reporting_endpoints_header())

    def test_header_value(self):
        securityheaders.set_reporting_endpoint("csp", "/cspReport")
        securityheaders.set_reporting_endpoint("default", "https://example.com/reports")
        self.assertEqual(
            'csp="/cspReport", default="https://example.com/reports"',
            securityheaders._build_reporting_endpoints_header(),
        )


class TestCspReportingDirectives(ViURTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.csp_backup = copy.deepcopy(conf.security.content_security_policy)
        # addCspRule refuses to run once the app has been built, which other tests in this suite may have done
        self.main_app_backup = conf.main_app
        conf.main_app = None

    def tearDown(self) -> None:
        conf.security.content_security_policy = self.csp_backup
        conf.main_app = self.main_app_backup
        super().tearDown()

    def test_report_to_holds_a_single_token(self):
        securityheaders.addCspRule("report-to", "old-endpoint", "enforce")
        securityheaders.addCspRule("report-to", "csp", "enforce")
        self.assertEqual(["csp"], conf.security.content_security_policy["enforce"]["report-to"])

    def test_report_uri_holds_a_single_url(self):
        securityheaders.addCspRule("report-uri", "/old", "enforce")
        securityheaders.addCspRule("report-uri", "/cspReport", "enforce")
        self.assertEqual(["/cspReport"], conf.security.content_security_policy["enforce"]["report-uri"])

    def test_report_to_without_endpoint_warns(self):
        securityheaders.addCspRule("report-to", "unknown", "enforce")
        with self.assertLogs(level="WARNING") as logs:
            securityheaders._validate_reporting_config()
        self.assertIn("'unknown'", "".join(logs.output))

    def test_report_to_with_endpoint_is_silent(self):
        securityheaders.set_reporting_endpoint("csp", "/cspReport")
        self.addCleanup(securityheaders.set_reporting_endpoint, "csp", None)
        securityheaders.addCspRule("report-to", "csp", "enforce")
        with self.assertNoLogs(level="WARNING"):
            securityheaders._validate_reporting_config()

    def test_dev_server_warns_about_http_endpoints(self):
        securityheaders.set_reporting_endpoint("csp", "/cspReport")
        self.addCleanup(securityheaders.set_reporting_endpoint, "csp", None)
        securityheaders.addCspRule("report-to", "csp", "enforce")
        with mock.patch.object(type(conf.instance), "is_dev_server", True):
            with self.assertLogs(level="WARNING") as logs:
                securityheaders._validate_reporting_config()
        self.assertIn("https", "".join(logs.output))

    def test_reporting_directives_are_not_quoted(self):
        securityheaders.addCspRule("report-to", "csp", "enforce")
        securityheaders.addCspRule("report-uri", "/cspReport", "enforce")
        securityheaders._rebuildCspHeaderCache()
        header = conf.security.content_security_policy["_headerCache"]["Content-Security-Policy"]
        self.assertIn("report-to csp; ", header)
        self.assertIn("report-uri /cspReport; ", header)
