from abstract import ViURTestCase


class TestHTTPExceptions(ViURTestCase):
    """All HTTP exception classes: status codes, default descriptions, custom messages."""

    def _assert_http(self, exc_cls, expected_status):
        exc = exc_cls()
        self.assertIsInstance(exc, exc_cls)
        self.assertEqual(expected_status, exc.status)

    def test_bad_request(self):
        from viur.core.errors import BadRequest
        exc = BadRequest()
        self.assertEqual(400, exc.status)

    def test_bad_request_custom_descr(self):
        from viur.core.errors import BadRequest
        exc = BadRequest("custom message")
        self.assertEqual(400, exc.status)
        self.assertIn("custom message", exc.descr)

    def test_unauthorized(self):
        from viur.core.errors import Unauthorized
        self._assert_http(Unauthorized, 401)

    def test_payment_required(self):
        from viur.core.errors import PaymentRequired
        self._assert_http(PaymentRequired, 402)

    def test_forbidden(self):
        from viur.core.errors import Forbidden
        self._assert_http(Forbidden, 403)

    def test_not_found(self):
        from viur.core.errors import NotFound
        self._assert_http(NotFound, 404)

    def test_method_not_allowed(self):
        from viur.core.errors import MethodNotAllowed
        self._assert_http(MethodNotAllowed, 405)

    def test_not_acceptable(self):
        from viur.core.errors import NotAcceptable
        self._assert_http(NotAcceptable, 406)

    def test_request_timeout(self):
        from viur.core.errors import RequestTimeout
        self._assert_http(RequestTimeout, 408)

    def test_gone(self):
        from viur.core.errors import Gone
        self._assert_http(Gone, 410)

    def test_precondition_failed(self):
        from viur.core.errors import PreconditionFailed
        self._assert_http(PreconditionFailed, 412)

    def test_request_too_large(self):
        from viur.core.errors import RequestTooLarge
        self._assert_http(RequestTooLarge, 413)

    def test_unprocessable_entity(self):
        from viur.core.errors import UnprocessableEntity
        self._assert_http(UnprocessableEntity, 422)

    def test_locked(self):
        from viur.core.errors import Locked
        self._assert_http(Locked, 423)

    def test_too_many_requests(self):
        from viur.core.errors import TooManyRequests
        self._assert_http(TooManyRequests, 429)

    def test_censored(self):
        from viur.core.errors import Censored
        self._assert_http(Censored, 451)

    def test_internal_server_error(self):
        from viur.core.errors import InternalServerError
        self._assert_http(InternalServerError, 500)

    def test_not_implemented(self):
        from viur.core.errors import NotImplemented
        self._assert_http(NotImplemented, 501)

    def test_bad_gateway(self):
        from viur.core.errors import BadGateway
        self._assert_http(BadGateway, 502)

    def test_service_unavailable(self):
        from viur.core.errors import ServiceUnavailable
        self._assert_http(ServiceUnavailable, 503)


class TestRedirect(ViURTestCase):

    def test_redirect_url_stored(self):
        from viur.core.errors import Redirect
        exc = Redirect("/home")
        self.assertEqual("/home", exc.url)
        self.assertEqual(303, exc.status)

    def test_redirect_301(self):
        from viur.core.errors import Redirect
        exc = Redirect("/old", status=301)
        self.assertEqual(301, exc.status)

    def test_redirect_302(self):
        from viur.core.errors import Redirect
        exc = Redirect("/old", status=302)
        self.assertEqual(302, exc.status)

    def test_redirect_invalid_status_raises(self):
        from viur.core.errors import Redirect
        with self.assertRaises(ValueError):
            Redirect("/home", status=200)

    def test_redirect_404_raises(self):
        from viur.core.errors import Redirect
        with self.assertRaises(ValueError):
            Redirect("/home", status=404)
