import types
import unittest

import webob

from abstract import ViURTestCase


class TestSecurityHeaders(ViURTestCase):
    def setUp(self):
        super().setUp()
        from viur.core.config import conf
        conf.strict_mode = False

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
