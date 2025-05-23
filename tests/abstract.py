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
        self.testbed.deactivate()
