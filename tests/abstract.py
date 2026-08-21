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
        # ContextVars outlive the test case that set them. A leaked current.request
        # in particular makes CallDeferred queue a task on the stale request instead
        # of running it inline, which silently breaks unrelated tests later in the
        # run. Imported here because viur.core is not importable at collection time.
        from viur.core import current
        for context_var in (
            current.request, current.request_data, current.session, current.language, current.user,
        ):
            context_var.set(None)

        self.testbed.deactivate()
