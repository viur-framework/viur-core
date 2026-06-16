import types

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
