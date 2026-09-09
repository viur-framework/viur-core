import copy
import types
from unittest import mock

import webob

from abstract import ViURTestCase


class TestSecurityHeaders(ViURTestCase):
    def setUp(self):
        super().setUp()
        from viur.core.config import conf
        conf.strict_mode = False
        # add_csp_rule asserts the app hasn't been built yet (conf.main_app is None).
        # Other tests in the full suite may leave conf.main_app set, so snapshot and reset it.
        self._orig_main_app = conf.main_app
        conf.main_app = None

    def tearDown(self):
        from viur.core.config import conf
        conf.main_app = self._orig_main_app
        super().tearDown()

    def _fresh_security(self):
        """A standalone Security instance that does not mutate shared class defaults."""
        from viur.core.config import Security
        sec = Security()
        # detach mutable members we will mutate in tests from the class-level defaults
        sec.content_security_policy = None
        sec.permissions_policy = {}
        return sec

    def test_enable_strict_transport_security(self):
        sec = self._fresh_security()
        sec.enable_strict_transport_security(max_age=10, include_sub_domains=True, preload=True)
        self.assertEqual(sec.strict_transport_security, "max-age=10; includeSubDomains; preload")

    def test_set_x_frame_options(self):
        sec = self._fresh_security()
        sec.set_x_frame_options("off")
        self.assertIsNone(sec.x_frame_options)
        sec.set_x_frame_options("sameorigin")
        self.assertEqual(sec.x_frame_options, ("sameorigin", None))
        sec.set_x_frame_options("allow-from", "https://example.com")
        self.assertEqual(sec.x_frame_options, ("allow-from", "https://example.com"))
        with self.assertRaises(ValueError):
            sec.set_x_frame_options("allow-from", "ftp://nope")

    def test_set_x_xss_protection(self):
        sec = self._fresh_security()
        sec.set_x_xss_protection(None)
        self.assertIsNone(sec.x_xss_protection)
        sec.set_x_xss_protection(True)
        self.assertIs(sec.x_xss_protection, True)
        sec.set_x_xss_protection(False)
        self.assertIs(sec.x_xss_protection, False)
        with self.assertRaises(ValueError):
            sec.set_x_xss_protection("yes")

    def test_set_x_content_type_no_sniff(self):
        sec = self._fresh_security()
        sec.set_x_content_type_no_sniff(False)
        self.assertFalse(sec.x_content_type_options)
        with self.assertRaises(ValueError):
            sec.set_x_content_type_no_sniff(None)

    def test_set_x_permitted_cross_domain_policies(self):
        sec = self._fresh_security()
        sec.set_x_permitted_cross_domain_policies("master-only")
        self.assertEqual(sec.x_permitted_cross_domain_policies, "master-only")
        with self.assertRaises(ValueError):
            sec.set_x_permitted_cross_domain_policies("bogus")

    def test_set_referrer_policy(self):
        sec = self._fresh_security()
        sec.set_referrer_policy("no-referrer")
        self.assertEqual(sec.referrer_policy, "no-referrer")
        with self.assertRaises(AssertionError):
            sec.set_referrer_policy("bogus")

    def test_set_permission_policy_directive(self):
        sec = self._fresh_security()
        sec.permissions_policy = {}
        sec.set_permission_policy_directive("camera", ["self"])
        self.assertEqual(sec.permissions_policy["camera"], ["self"])

    def test_set_cross_origin_isolation(self):
        sec = self._fresh_security()
        sec.set_cross_origin_isolation(True, "same-origin", "same-site")
        self.assertTrue(sec.enable_coep)
        self.assertEqual(sec.enable_coop, "same-origin")
        self.assertEqual(sec.enable_corp, "same-site")
        with self.assertRaises(AssertionError):
            sec.set_cross_origin_isolation(True, "bogus", "same-site")

    def test_add_csp_rule_and_build(self):
        sec = self._fresh_security()
        sec.add_csp_rule("default-src", "self", "enforce")
        sec.add_csp_rule("img-src", "storage.googleapis.com", "enforce")
        sec.add_csp_rule("script-src", "self", "monitor")
        sec._build_csp_header_cache()
        enforce = sec._csp_header_cache["Content-Security-Policy"]
        self.assertIn("default-src 'self'; ", enforce)
        self.assertIn("img-src storage.googleapis.com; ", enforce)
        report_only = sec._csp_header_cache["Content-Security-Policy-Report-Only"]
        self.assertIn("script-src 'self'; ", report_only)

    def test_add_csp_rule_invalid(self):
        sec = self._fresh_security()
        with self.assertRaises(AssertionError):
            sec.add_csp_rule("default-src", "self", "bogus-mode")
        with self.assertRaises(AssertionError):
            sec.add_csp_rule("default-src", "ev'il", "enforce")
        with self.assertRaises(AssertionError):
            sec.add_csp_rule("scripts-src", "self", "enforce")  # unknown directive

    def test_build_csp_header_cache_empty(self):
        sec = self._fresh_security()  # content_security_policy is None
        sec._build_csp_header_cache()
        self.assertEqual(sec._csp_header_cache, {})

    def test_build_permissions_policy_header(self):
        sec = self._fresh_security()
        sec.permissions_policy = {"autoplay": ["self"], "camera": []}
        sec._build_permissions_policy_header()
        self.assertEqual(sec._permissions_policy_header, "autoplay=(self), camera=()")

    def test_extend_csp_quotes_nonce(self):
        from viur.core import current
        sec = self._fresh_security()
        sec.content_security_policy = {"enforce": {"default-src": ["self"]}}

        holder = types.SimpleNamespace(response=webob.Response())
        token = current.request.set(holder)
        try:
            sec.extend_csp({"style-src": ["nonce-abc"]})
        finally:
            current.request.reset(token)

        csp = holder.response.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'; ", csp)
        self.assertIn("style-src 'nonce-abc'; ", csp)  # per-request CSP DOES quote nonce-

    def test_finalize_builds_and_validates(self):
        sec = self._fresh_security()
        sec.content_security_policy = {"enforce": {"default-src": ["self"]}}
        sec.permissions_policy = {"autoplay": ["self"]}
        sec.finalize()
        self.assertEqual(sec._csp_header_cache["Content-Security-Policy"], "default-src 'self'; ")
        self.assertEqual(sec._permissions_policy_header, "autoplay=(self)")

    def test_finalize_rejects_bad_hsts(self):
        sec = self._fresh_security()
        sec.strict_transport_security = "nonsense"
        with self.assertRaises(AssertionError):
            sec.finalize()

    def test_finalize_rejects_bad_cross_domain(self):
        sec = self._fresh_security()
        sec.x_permitted_cross_domain_policies = "bogus"
        with self.assertRaises(AssertionError):
            sec.finalize()

    def test_update_response_headers_full(self):
        sec = self._fresh_security()
        sec.content_security_policy = {"enforce": {"default-src": ["self"]}}
        sec.permissions_policy = {"autoplay": ["self"]}
        sec.finalize()
        resp = webob.Response()
        sec.update_response_headers(resp, is_ssl=True)
        self.assertEqual(resp.headers["Content-Security-Policy"], "default-src 'self'; ")
        self.assertEqual(resp.headers["Strict-Transport-Security"], sec.strict_transport_security)
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp.headers["Referrer-Policy"], sec.referrer_policy)
        self.assertEqual(resp.headers["Permissions-Policy"], "autoplay=(self)")
        self.assertEqual(resp.headers["X-Frame-Options"], "sameorigin")

    def test_update_response_headers_no_hsts_without_ssl(self):
        sec = self._fresh_security()
        sec.finalize()
        resp = webob.Response()
        sec.update_response_headers(resp, is_ssl=False)
        self.assertNotIn("Strict-Transport-Security", resp.headers)

    def test_build_csp_header_cache_does_not_quote_nonce(self):
        sec = self._fresh_security()
        sec.content_security_policy = {"enforce": {"style-src": ["nonce-abc"]}}
        sec._build_csp_header_cache()
        csp = sec._csp_header_cache["Content-Security-Policy"]
        # project-wide CSP must NOT quote nonce- (a nonce must not be reused across requests)
        self.assertIn("style-src nonce-abc; ", csp)
        self.assertNotIn("'nonce-abc'", csp)

    def test_add_csp_rule_rejected_after_app_built(self):
        from viur.core.config import conf
        sec = self._fresh_security()
        original = conf.main_app
        conf.main_app = object()  # simulate "app already built"
        try:
            with self.assertRaises(AssertionError):
                sec.add_csp_rule("default-src", "self", "enforce")
        finally:
            conf.main_app = original

    def test_module_shims_warn_and_delegate(self):
        from viur.core import securityheaders
        from viur.core.config import conf
        original = conf.security.referrer_policy
        try:
            with self.assertWarns(DeprecationWarning):
                securityheaders.setReferrerPolicy("origin")
            self.assertEqual(conf.security.referrer_policy, "origin")
        finally:
            conf.security.referrer_policy = original

    def test_module_valid_referrer_policies_alias(self):
        from viur.core import securityheaders
        from viur.core.config import conf
        self.assertEqual(securityheaders.validReferrerPolicies, conf.security.VALID_REFERRER_POLICIES)

    def test_debug_trace_headers_defaults(self):
        from viur.core.config import conf
        self.assertFalse(conf.debug.trace_headers)
        self.assertIn("Cookie", conf.debug.trace_headers_redact)
        self.assertIn("Authorization", conf.debug.trace_headers_redact)

    def test_redact_headers(self):
        from viur.core.request import _redact_headers
        headers = {"Cookie": "secret", "X-Foo": "bar", "set-cookie": "s"}
        redacted = _redact_headers(headers, ("Cookie", "Set-Cookie"))
        self.assertEqual(redacted["Cookie"], "[redacted]")
        self.assertEqual(redacted["set-cookie"], "[redacted]")  # case-insensitive
        self.assertEqual(redacted["X-Foo"], "bar")

    def test_redact_headers_empty_list_is_raw(self):
        from viur.core.request import _redact_headers
        headers = {"Cookie": "secret"}
        self.assertEqual(_redact_headers(headers, ())["Cookie"], "secret")

    def test_extend_csp_override_and_remove(self):
        from viur.core import current
        sec = self._fresh_security()
        sec.content_security_policy = {"enforce": {"default-src": ["self"], "img-src": ["self"]}}
        holder = types.SimpleNamespace(response=webob.Response())
        token = current.request.set(holder)
        try:
            sec.extend_csp(override_rules={"default-src": ["none"], "img-src": None})
        finally:
            current.request.reset(token)
        csp = holder.response.headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'; ", csp)
        self.assertNotIn("img-src", csp)

    def test_extend_csp_with_no_project_csp(self):
        from viur.core import current
        sec = self._fresh_security()  # content_security_policy is None
        holder = types.SimpleNamespace(response=webob.Response())
        token = current.request.set(holder)
        try:
            sec.extend_csp({"style-src": ["self"]})
        finally:
            current.request.reset(token)
        self.assertIn("style-src 'self'; ", holder.response.headers["Content-Security-Policy"])

    def test_audit_headers_logs_redacted(self):
        from viur.core import request
        from viur.core.config import conf
        original = conf.debug.trace_headers_redact
        conf.debug.trace_headers_redact = ("Cookie", "Set-Cookie")
        try:
            fake = types.SimpleNamespace(
                request=types.SimpleNamespace(headers={"Cookie": "secret", "X-Foo": "bar"}),
                response=types.SimpleNamespace(headers={"Set-Cookie": "s", "X-Bar": "baz"}),
            )
            with self.assertLogs(level="DEBUG") as cm:
                request.Router._audit_headers(fake)
            blob = "\n".join(cm.output)
            self.assertIn("[redacted]", blob)
            self.assertNotIn("secret", blob)
            self.assertIn("bar", blob)
        finally:
            conf.debug.trace_headers_redact = original


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
