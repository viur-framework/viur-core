from unittest import mock

from abstract import ViURTestCase


def index(self):
    """A stand-in for an ``@exposed`` method wrapped by ``ResponseCache``."""
    return "cached"


class TestResponseCacheTimezoneSensitive(ViURTestCase):
    """``timezone_sensitive`` adds the request's guessed timezone to the cache key."""

    @staticmethod
    def _fake_request(country: str | None) -> None:
        from viur.core import current

        request = mock.Mock()
        request.request.headers = {"X-Appengine-Country": country} if country else {}
        request.template_style = None
        current.request.set(request)
        current.request_data.set({})

    def _args(self, cache, country: str | None) -> dict:
        self._fake_request(country)
        return cache.get_args(func=index, path="/", args=(), kwargs={})

    def test_default_key_has_no_timezone(self):
        from viur.core.cache import ResponseCache

        self.assertNotIn("__timezone", self._args(ResponseCache(), "DE"))

    def test_timezone_sensitive_adds_guessed_timezone(self):
        from viur.core.cache import ResponseCache

        args = self._args(ResponseCache(timezone_sensitive=True), "DE")
        self.assertEqual(args["__timezone"], "Europe/Berlin")

    def test_requests_from_different_timezones_get_different_keys(self):
        from viur.core.cache import ResponseCache

        cache = ResponseCache(timezone_sensitive=True)
        key_de = cache.get_string_from_args(self._args(cache, "DE"))
        key_us = cache.get_string_from_args(self._args(cache, "US"))
        key_unknown = cache.get_string_from_args(self._args(cache, None))
        self.assertNotEqual(key_de, key_us)
        self.assertNotEqual(key_de, key_unknown)
        # and the same timezone hits the same entry
        self.assertEqual(key_de, cache.get_string_from_args(self._args(cache, "DE")))

    def test_default_settings_apply(self):
        from viur.core.cache import DEFAULT_SETTINGS, ResponseCache

        self.assertFalse(ResponseCache().timezone_sensitive)
        with mock.patch.object(DEFAULT_SETTINGS, "timezone_sensitive", True):
            self.assertTrue(ResponseCache().timezone_sensitive)
            self.assertFalse(ResponseCache(timezone_sensitive=False).timezone_sensitive)
