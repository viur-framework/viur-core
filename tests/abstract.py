import contextvars
import os
import unittest
from unittest import mock

from google.appengine.ext import testbed


class ViURTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_all_stubs()

        # There's not testbed for google.auth, so we need to mock this by our own
        import google.auth
        google.auth.default = mock.Mock(return_value=(mock.Mock(), os.getenv("GOOGLE_CLOUD_PROJECT")))

    def tearDown(self) -> None:
        self._reset_context_vars()
        self.testbed.deactivate()

    @staticmethod
    def _reset_context_vars() -> None:
        """Clear the context variables of :mod:`viur.core.current`.

        They live for as long as the process does, so a request or session left behind by one
        test is still in place for every test running after it. That silently changes what the
        code under test sees -- a request in the context can, for instance, turn a direct call
        into a deferred one.
        """
        from viur.core import current

        for value in vars(current).values():
            if isinstance(value, contextvars.ContextVar):
                value.set(None)
