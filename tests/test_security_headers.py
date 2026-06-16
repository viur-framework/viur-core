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
