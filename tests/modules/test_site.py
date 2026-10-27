from unittest import mock

from abstract import ViURTestCase


class TestSiteIndex(ViURTestCase):
    """Regression tests for :meth:`Site.index`."""

    def test_path_traversal_template_is_not_found(self):
        from viur.core import errors
        from viur.core.modules.site import Site

        site = Site("s", "s")
        site.render = mock.Mock()

        for template in ("../x", "a/b"):
            with self.subTest(template=template):
                with self.assertRaises(errors.NotFound):
                    site.index(template=template)

        # rejected before the renderer is even asked for a template
        site.render.getEnv.assert_not_called()
