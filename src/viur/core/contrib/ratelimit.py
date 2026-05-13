"""
Request-level rate limiter using App Engine Memcache.

Registers as a :class:`~viur.core.request.RequestValidator` and therefore
runs *before* any session, routing, or handler logic — making it the
earliest possible place to shed excess traffic.

Guests are identified by their IP address (IPv6 addresses are bucketed into
/64 prefixes so that a single host cannot trivially rotate around the limit).
Authenticated users are identified by their Datastore user key.

Usage::

    from viur.core.request import Router
    from viur.core.contrib.ratelimit import RequestRateLimit, TimeWindow

    Router.requestValidators.append(
        RequestRateLimit(
            rate_for_guests=TimeWindow(limit=200, time_window=60),
            rate_for_users=TimeWindow(limit=500, time_window=60),
        )
    )
"""
import dataclasses
import ipaddress
import logging
import time
import typing as t

from google.appengine.api.memcache import Client

from viur.core import current
from viur.core.request import RequestValidator, Router

logger = logging.getLogger(__name__)

_memcache = Client()


@dataclasses.dataclass(frozen=True)
class TimeWindow:
    """Rate-limit budget for a single time window.

    :param limit: Maximum number of requests allowed within *time_window*.
    :param time_window: Length of the window in seconds.
    """
    limit: int
    time_window: int


class RequestRateLimit(RequestValidator):
    """Global HTTP request rate limiter.

    Enforces separate budgets for anonymous (guest) and authenticated
    requests.  When the budget is exceeded the validator returns HTTP 429
    and sets the ``Retry-After`` header so clients know when to retry.

    :param rate_for_guests: Budget applied to unauthenticated requests.
    :param rate_for_users: Budget applied to authenticated requests.
    :param namespace: Memcache namespace used for all rate-limit keys.
    """

    name = "RequestRateLimit"

    def __init__(
        self,
        rate_for_guests: TimeWindow = TimeWindow(limit=1000, time_window=60),
        rate_for_users: TimeWindow = TimeWindow(limit=2000, time_window=60),
        namespace: str = "viur_rate_limit",
    ):
        self.rate_for_guests = rate_for_guests
        self.rate_for_users = rate_for_users
        self.namespace = namespace

    def validate(self, request: "Router") -> t.Optional[tuple[int, str, str]]:
        if request.is_deferred:
            return None  # Task Queue requests are always allowed

        if user := current.user.get():
            client_id = str(user["key"])
            rate = self.rate_for_users
        else:
            client_id = self._get_request_ip()
            rate = self.rate_for_guests

        current_time = time.time() / rate.time_window
        key = f"rate_limit:{client_id}:{int(current_time)}"

        count = _memcache.get(key, namespace=self.namespace)
        logger.debug(f"rate limit check: {client_id=} {count=} limit={rate.limit}")

        if count is None:
            _memcache.add(key, 1, time=rate.time_window, namespace=self.namespace)
            return None

        if count < rate.limit:
            _memcache.incr(key, initial_value=1, namespace=self.namespace)
            return None

        # Budget exhausted — tell the client when the current window expires.
        seconds_into_window = (current_time - int(current_time)) * rate.time_window
        retry_after = int(rate.time_window - seconds_into_window)
        request.response.headers["Retry-After"] = str(retry_after)
        return 429, "Too Many Requests", "Too Many Requests. Please try again later."

    @staticmethod
    def _get_request_ip() -> str:
        """Return a stable client identifier derived from the remote address.

        IPv4 addresses are returned as-is.  For IPv6 the /64 network prefix
        is returned so that a single host cannot trivially rotate its
        interface identifier to bypass the limit.
        """
        raw = current.request.get().request.remote_addr
        ip = ipaddress.ip_address(raw)

        if isinstance(ip, ipaddress.IPv4Address):
            return str(ip)

        if isinstance(ip, ipaddress.IPv6Address):
            return str(ipaddress.IPv6Network((ip, 64), strict=False))

        raise NotImplementedError(f"Unsupported IP version: {ip!r}")
