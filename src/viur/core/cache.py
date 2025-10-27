"""
This module implements a cache that can be used to serve entire requests or cache the output of any function
(as long it's result can be stored in datastore). The intended use is to wrap functions that can be called from
the outside (@exposed) with the @ResponseCache decorator. This will enable the cache provided in this module for that
function, intercepting all calls to this function and serve a cached response instead of calling the function if
possible. Authenticated users with "root" access can always bypass this cache by sending the X-Viur-Disable-Cache
http Header along with their requests. Entities in this cache will expire if
    - Their TTL is exceeded
    - They're explicitly removed from the cache by calling :meth:`viur.core.cache.flushCache` using their path
    - A Datastore entity that has been accessed using db.get() from within the cached function has been modified
    - The wrapped function has run a query over a kind in which an entity has been added/edited/deleted

..Warning: As this cache is intended to be used with exposed functions, it will not only store the result of the
    wrapped function, but will also store and restore the Content-Type http header. This can cause unexpected
    behaviour if it's used to cache the result of non top-level functions, as calls to these functions now may
    cause this header to be rewritten.
"""

import collections
import enum
import inspect
import logging
import os
import sys
import typing as t
import zlib
from datetime import timedelta as td
from functools import wraps
from hashlib import sha512

from viur.core import Method, conf, current, db, errors, utils, tasks
from viur.core.config import ConfigType
from webob.datetime_utils import serialize_date

logger = logging.getLogger(__name__)
if logger.level == logging.NOTSET:
    logger.setLevel(logging.INFO)

__all__ = [
    "UserSensitive",
    "BypassCache",
    "ResponseCache",
    "DEFAULT_SETTINGS",
    "DEFAULT_COMPRESSION",
    "CACHE_KINDNAME",
    "flushCache",
]

CACHE_KINDNAME: t.Final[str] = "viur-cache"

MAX_PROPERTY_SIZE: t.Final[int] = 1024 ** 2 - 89
"""Maximal possible property size in a datastore entity"""


class UserSensitive(enum.IntEnum):
    """
    Signals wherever the output of the wrapped method depends on the current user.
    """

    IGNORE = enum.auto()
    """independent of wherever the user is a guest or known, all will get the same content."""

    GUEST_ONLY = enum.auto()
    """cache only for guests, no cache will be performed if the user is logged-in."""

    BOTH = enum.auto()
    """cache in two groups, one for guests and one for all users"""

    INDIVIDUAL = enum.auto()
    """cache the result of that function for each individual users separately."""


BypassCache = collections.namedtuple("BypassCache", ["reason"])
"""Class to signal that the request should not be cached with a reason"""

_SENTINEL = enum.Enum("_SENTINEL", "sentinel")
sentinel = _SENTINEL.sentinel  # noqa
"""Sentinel for not provided argument (signal to merge value from default settings)"""

Args = t.ParamSpec("Args")
"""type hint for func arguments"""
Value = t.TypeVar("Value")
"""type hint for func response (request response)"""

DEFAULT_COMPRESSION = zlib.Z_DEFAULT_COMPRESSION
"""Default compression (alias for zlib.Z_DEFAULT_COMPRESSION)"""


class DefaultSettings(ConfigType):
    """
    Singleton settings container type to hold global settings.

    Instead of repeating argument in every @ResponseCache decorator
    settings can be set here once.
    Argument provided directly to @ResponseCache will always have priority.
    """

    language_sensitive: bool = False
    user_sensitive: UserSensitive = UserSensitive.IGNORE
    max_cache_time: td | None = None
    compression_level: int = None
    evaluated_args: list[str] | tuple[str, ...] = tuple()
    renderer: list[str | t.Type] | tuple[str | t.Type, ...] = None

    raise_too_large: bool = False
    """
    If the response is too large to cache and this option is True, an exception is raised.
    If it's False, the uncached response is returned to ensure response delivery.
    """


DEFAULT_SETTINGS = DefaultSettings(strict_mode=True)
"""The global instance of DefaultSettings"""


class ResponseCache(t.Generic[Args, Value]):
    """
    Decorator class to cache the result of the reponse.

    ResponseCache caches:
    - Normal 200 responses, regardless of the content-type
        - Including headers changed by the wrapped function
    - Redirects 3**

    Parameters can control what and how long it should be cached,
    see the descriptions in :meth:`__init__`.

    Example usage:

    >>> from viur.core import exposed
    >>> import datetime
    >>> @exposed
    >>> @ResponseCache(max_cache_time=datetime.timedelta(days=1))
    >>> def index(self):
    >>>     return f"This result was cached at {datetime.datetime.now()}"
    """

    __slots__ = (
        "compression_level",
        "evaluated_args",
        "language_sensitive",
        "max_cache_time",
        "renderer",
        "urls",
        "user_sensitive",
    )

    REDIRECT_FLAG = "<<REDIRECT>>"
    """
    Flag used as content-type to signal that this is a cached redirect instead of a normal response.
    """

    def __init__(
        self,
        *,
        urls: list[str] | tuple[str, ...] | None = None,
        renderer: list[str | t.Type] | tuple[str | t.Type, ...] | None = sentinel,
        user_sensitive: UserSensitive = sentinel,
        language_sensitive: bool = sentinel,
        evaluated_args: list[str] | tuple[str, ...] = sentinel,
        max_cache_time: td | None = sentinel,
        compression_level: int = sentinel,
    ):
        """
        Create a ResponseCache instance

        :param urls:
            A list of urls for this function, for which the cache should be enabled.
            A method can have several urls (e.g. /page/view, /pdf/page/view or /pdf/seite/view),
            and it might should not be cached under all urls (e.g. /vi/page/view).
            If the parameter is omitted, the URL is ignored for the check and the call is saved in the cache
            (unless excluded by other parameters), regardless of the path via which the method was called.
        :param renderer:
            This parameter can be used to specify render names (such as html, json)
            under which the result should be cached.
            The parameter can be used as an alternative to the `url` parameter, but can also be used in addition.
        :param user_sensitive:
            Signals wherever the output of the wrapped method depends on the current user.
            Look at :class:`UserSensitive` for parameter descriptions.
        :param language_sensitive:
            If True, signals that the output of the wrapped method should
            be cached separately for each language (because it's translated).
        :param evaluated_args:
            List of argument name having influence to the output generated by that wrapped method.
            This list *must* be complete! Parameters not named here are ignored!
            Warning: Double-check this list! F.e. if that function generates a list of entries and
            you miss the parameter "order" here, it would be impossible to sort the list.
            It would always have the ordering it had when the cache-entry was created.
            If the wrapped method use variable positional arguments (*args)
            or variable keyword arguments (**kwargs) you can include "arg" and/or "kwargs"
            to this list to accept all variable arguments that are passed by these.
            If only certain parameters of **kwargs should be considered add the key like it
            would be a explicit positional or keyword argument.
        :param max_cache_time:
            Specifies the maximum time an entry stays in the cache.
            Note: It's not erased from the database after that time, but it won't be served anymore.
            If None, the cache stays valid forever (until manually erased by calling flushCache).
        :param compression_level:
            Large pages may be too big for the datastore (max. approx. 1 MB, but including meta data).
            If this parameter is activated, the page is compressed before it is saved in the entity.
            Possible values for setting the compression level are the numbers 0 - 9.
            Compression is deactivated with None.
            See also :param:`DEFAULT_SETTINGS.raise_too_large`.
        """
        # Use default values if a argument was not provided
        if renderer is sentinel:
            renderer = DEFAULT_SETTINGS.renderer
        if user_sensitive is sentinel:
            user_sensitive = DEFAULT_SETTINGS.user_sensitive
        if language_sensitive is sentinel:
            language_sensitive = DEFAULT_SETTINGS.language_sensitive
        if evaluated_args is sentinel:
            evaluated_args = DEFAULT_SETTINGS.evaluated_args
        if max_cache_time is sentinel:
            max_cache_time = DEFAULT_SETTINGS.max_cache_time
        if compression_level is sentinel:
            compression_level = DEFAULT_SETTINGS.compression_level
        self.urls = urls
        self.renderer: list[str | t.Type] | tuple[str | t.Type, ...] | None = renderer
        self.user_sensitive: UserSensitive = user_sensitive
        self.language_sensitive: bool = language_sensitive
        self.evaluated_args: list[str] | tuple[str, ...] = evaluated_args
        if max_cache_time is None:
            self.max_cache_time: None = None
        else:
            self.max_cache_time: td = utils.parse.timedelta(max_cache_time)
        self.compression_level: int | None = compression_level

    def __call__(this, func: t.Callable[Args, Value]) -> Value:
        """
        Does the actual work of wrapping a callable @exposed method
        and return a internal wrapper.
        """

        method = None
        if isinstance(func, Method):
            # Wrapping an (exposed) Method; continue with Method._func
            method = func
            func = func._func

        @wraps(func)
        def wrapper(self, *args: Args.args, **kwargs: Args.kwargs) -> Value:
            """
            Wrapper which is called if the route is called
            and returns a cached response or caches the response (and return it)
            """
            current_request = current.request.get()
            logger.debug(f"Call {func} via {this}")

            def bypass_response() -> Value:
                """Call the func, set bybass and no-cache headers and return it"""
                try:
                    response = func(self, *args, **kwargs)
                finally:
                    current_request.response.headers["X-Cache-Status"] = "BYPASS"
                    current_request.response.headers["Cache-Control"] = "no-cache"
                return response

            if conf.debug.disable_cache or current_request.disableCache:
                if conf.debug.disable_cache:
                    logger.debug("Caching is disabled by config")
                return bypass_response()

            # logger.debug(f"{utils.vars_full(current_request)=}")

            # How many arguments are part of the way to the function called (and how many are just *args)
            offset = -len(current_request.args) or len(current_request.path_list)
            # Get just the path segment before the arguments (the @exposed route)
            path = "/".join(current_request.path_list[:offset])
            path = f"/{path.strip('/')}"  # normalize /
            logger.debug(f"{path=}")

            if this.urls is not None and path not in this.urls:
                logger.debug(f"{path} is not {this.urls} and should not be cached")
                return bypass_response()

            if this.renderer is None:
                logger.debug(f"Request should be cached on all renderers (not specified)")
            elif (renderer := getattr(self, "render", "NOT_SET")) is None or renderer == "NOT_SET":
                logger.error(f"{self}.render is {renderer}, skipping this check")
            else:
                is_allowed_renderer = (
                    (isinstance(r, str) and r == self.render.kind)  # Renderer kind provided (str)
                    or (not isinstance(r, str) and isinstance(self.render, r))  # Renderer cls provided (type)
                    for r in this.renderer
                )
                if not any(is_allowed_renderer):
                    logger.debug(f"{self.render} with {self.render.kind=} should not be cached (only {this.renderer})")
                    return bypass_response()
                logger.debug(f"{self.render} should be cached")

            """
            try:
                logger.debug(f"{self.seo_language_map=}")
            except AttributeError as exc:
                logger.exception(exc)
            try:
                logger.debug(f"{getattr(self, func.__name__).seo_language_map=}")
            except AttributeError as exc:
                logger.exception(exc)
            """
            # TODO: we could add an option to handle them as synonynms ...

            cache_args = this.get_args(func=func, path=path, args=args, kwargs=kwargs)
            if isinstance(cache_args, BypassCache):
                logger.info(f"This request should not be cached ({cache_args=})")
                return bypass_response()

            cache_key = this.get_string_from_args(cache_args)
            logger.debug(f"{cache_key=}")

            entity = db.get(db.Key(CACHE_KINDNAME, cache_key))
            cache_status = "MISS"
            if entity:
                if not this.max_cache_time or utils.utcNow() <= entity["creationdate"] + this.max_cache_time:
                    # We store it unlimited or the cache is fresh enough
                    logger.debug("This request was served from cache.")
                    for key, value in entity["header"].items():
                        logger.debug(f"Load header {key=} = {value=}")
                        current_request.response.headers[key] = value
                    current_request.response.headers["X-Cache-Status"] = "HIT"
                    if entity["content-type"] == this.REDIRECT_FLAG:
                        raise errors.Redirect(**entity["data"])
                    current_request.response.headers["Content-Type"] = entity["content-type"]
                    current_request.response.headers["Last-Modified"] = serialize_date(entity["creationdate"])
                    current_request.response.headers["X-Cache-Served"] = serialize_date(utils.utcNow())
                    current_request.response.headers["X-Cache-Key"] = str(entity.key.id_or_name)  # TODO: tmp
                    if entity["compression_level"] is not None:
                        return zlib.decompress(entity["data"]).decode("utf-8")
                    return entity["data"]
                logger.debug("Cache is too old")
                cache_status = "UPDATED"

            # we will store only additional headers, added in the func call
            old_headers = list(current_request.response.headers.keys())

            redirect = None

            # If we made it this far, the request wasn't cached or too old; we need to rebuild it
            old_access_log = db.startDataAccessLog()
            try:
                uncompressed_body = body = func(self, *args, **kwargs)
            except errors.Redirect as redirect_exc:
                redirect = redirect_exc  # assign to variable from outer scope
                logger.info("Got a redirect to cache")
                content_type = this.REDIRECT_FLAG
                uncompressed_body = body = {
                    "url": redirect.url,
                    "status": redirect.status,
                    "descr": redirect.descr,
                }
            else:
                content_type = current_request.response.headers["Content-Type"]
                body_size = uncompressed_size = sys.getsizeof(body)
                logger.debug(f"{uncompressed_size=}")

                if this.compression_level is not None:
                    body = zlib.compress(body.encode("utf-8"), this.compression_level)
                    body_size = compressed_size = sys.getsizeof(body)
                    logger.debug(f"{compressed_size=}")
                    logger.info(
                        f"Compression saved {uncompressed_size - compressed_size} bytes"
                        f" ({round((1 - compressed_size / uncompressed_size) * 100.0, 4)} %)"
                        f" ({uncompressed_size} --> {compressed_size})"
                    )

                if body_size > MAX_PROPERTY_SIZE:
                    # TODO: We should choose a good lower value, we need to store metadata too ...
                    logger.error("This response cannot be caches. It's too large")
                    if this.compression_level is None:
                        logger.error(f"Compression is disabled. Reduce the response size or enable it")
                    else:
                        logger.error(f"Reduce the response size or increase the compression level")

                    current_request.response.headers["X-Cache-Status"] = "TOO_LARGE"
                    if DEFAULT_SETTINGS.raise_too_large:
                        raise errors.InternalServerError("Response too large for caching")
                    return uncompressed_body
            finally:
                accessed_entries = db.endDataAccessLog(old_access_log)

            entity = db.Entity(db.Key(CACHE_KINDNAME, cache_key))
            entity["data"] = body
            entity["creationdate"] = utils.utcNow()
            entity["path"] = path
            entity["url"] = f"/{'/'.join(current_request.path_list)}"
            entity["content-type"] = content_type
            entity["accessedEntries"] = list(accessed_entries)
            entity["compression_level"] = this.compression_level
            headers = db.Entity()

            for key, value in current_request.response.headers.items():
                if (key.lower().startswith("x-") and key not in old_headers or key.lower() in {"cache-control"}):
                    logger.debug(f"Save header {key} = {value}")
                    headers[key] = value
                else:
                    logger.debug(f"Ignore header {key} = {value}")
            entity.exclude_from_indexes.add("data")
            entity.exclude_from_indexes.add("header")
            entity["header"] = headers
            entity = db.fix_unindexable_properties(entity)
            db.Put(entity)

            logger.debug("This request was a cache-miss. Cache has been updated.")
            current_request.response.headers["X-Cache-Status"] = cache_status
            current_request.response.headers["Last-Modified"] = serialize_date(entity["creationdate"])
            current_request.response.headers["X-Cache-Served"] = serialize_date(utils.utcNow())
            current_request.response.headers["X-Cache-Key"] = str(entity.key.id_or_name)  # TODO: tmp

            if content_type == this.REDIRECT_FLAG:
                raise redirect

            if this.compression_level is not None:
                # Return not the compressed body for the response
                return uncompressed_body
            return body

        if method is None:
            return wrapper
        else:
            method._func = wrapper
            return method

    def get_args(
        self,
        func: t.Callable,
        path: str,
        args: tuple,
        kwargs: dict,
    ) -> dict[str, t.Any] | BypassCache:
        """
        Create a argument dict to build the cache key.

        In addition to the arguments to be considered (evaluated_args) of the request,
        parameters are also formed from the other options of this class.
        """
        logger.debug(f"{args=} // {kwargs=} // {self.evaluated_args=} // {path=}")

        signature = inspect.signature(func)
        logger.debug(f"{signature=}")
        logger.debug(f"{signature.parameters=}")

        remaining_kwargs = kwargs.copy()
        res = {}

        for i, param in enumerate(signature.parameters.values()):
            if i == 0 and param.name == "self":
                continue
            # logger.debug(f"{i=} // {param.name=} // {param=} // {utils.vars_full(param)=}")
            if param.name not in self.evaluated_args:
                logger.debug(f"Ignoring {param=} (not in evaluated_args)")
            elif len(args) >= i and param.kind in {param.POSITIONAL_ONLY,
                                                   param.POSITIONAL_OR_KEYWORD} and param.name in self.evaluated_args:
                res[param.name] = args[i - 1]
            elif param.kind == param.VAR_POSITIONAL and param.name in self.evaluated_args:
                # *VAR_POSITIONAL must be always the last parameter before kwarg only parameters,
                # therefore we can consume the entire remaining args
                res[param.name] = args[i - 1:]
            elif param.kind == param.VAR_KEYWORD and param.name in self.evaluated_args:
                # **VAR_KEYWORDS must be always the last parameter,
                # therefore we can consume the entire remaining kwargs
                res |= remaining_kwargs
                remaining_kwargs.clear()
            elif param.name in remaining_kwargs and param.name in self.evaluated_args:
                res[param.name] = remaining_kwargs.pop(param.name)
            elif param.default is not param.empty and param.name in self.evaluated_args:
                res[param.name] = param.default
            else:
                # This case should never occur, but never say never ...
                logger.debug(f"Ignoring {param=}")

        # Last, merge remaining_kwargs in (passed as **VAR_KEYWORDS),
        # in this case, only certain and not all **VAR_KEYWORDS should be included.
        for key, value in remaining_kwargs.items():
            if key in self.evaluated_args:
                if key in res:
                    raise ValueError(f"Got duplicate {value=} for {key=}")
                res[key] = value
            else:
                logger.debug(f"Ignore {key=} : {value=} from remaining_kwargs")

        if self.user_sensitive != UserSensitive.IGNORE:
            user = current.user.get()
            if self.user_sensitive == UserSensitive.GUEST_ONLY and user:
                # We don't cache requests for each user separately
                return BypassCache("Cache is only for guests enabled")
            elif self.user_sensitive == UserSensitive.BOTH:
                res["__user"] = "__ISUSER" if user else None
            elif self.user_sensitive == UserSensitive.INDIVIDUAL:
                res["__user"] = user["key"] if user else None
            elif self.user_sensitive == UserSensitive.GUEST_ONLY:
                pass  # We don't need to store, that we're a guest.
            else:
                raise ValueError(f"Invalid value {self.user_sensitive=}")

        if self.language_sensitive:
            res["__lang"] = current.language.get()

        if conf.cache_environment_key:
            try:
                res["__cache_environment"] = conf.cache_environment_key()
            except RuntimeError as exc:
                logger.warning("Raising RuntimeError to bypass the cache is deprecated. "
                               "Please return a ByPassCache instance instead")
                res["__cache_environment"] = BypassCache(str(exc))
            if isinstance(res["__cache_environment"], BypassCache):
                return res["__cache_environment"]

        res["__path"] = path  # Different path might have different output (html,xml,..)

        logger.debug(f"{conf.instance.app_version=}")
        if conf.instance.is_dev_server:
            res["__app_version"] = f'dev_server_{os.getenv("USER", "")}'
        else:
            res["__app_version"] = conf.instance.app_version

        res["__template_style"] = current.request.get().template_style
        return res

    def get_string_from_args(self, args: dict[str, t.Any] | BypassCache) -> str | BypassCache:
        """Create a string key for the cache entity

        The parameters are sorted by key, and return as sha512 hash.

        :param args: The result of :meth:`get_args`
        """
        args = utils.freeze_dict(args)
        logger.debug(f"{args=}")
        return sha512(str(args).encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        """Representation of this class"""
        values = ", ".join(f"{key}={getattr(self, key)!r}" for key in self.__slots__)
        return f"<{type(self).__qualname__} with {values}>"


@tasks.CallDeferred
def flushCache(prefix: str = None, key: db.Key | None = None, kind:  str | None = None):
    """
        Flushes the cache. Its possible the flush only a part of the cache by specifying
        the path-prefix. The path is equal to the url that caused it to be cached (eg /page/view) and must be one
        listed in the 'url' param of :class:`ResponseCache`.

        :param prefix: Path or prefix that should be flushed.
        :param key: Flush all cache entries which may contain this key. Also flushes entries
            which executed a query over that kind.
        :param kind: Flush all cache entries which executed a query over that kind.

        Examples:
            - "/" would flush the main page (and only that),
            - "/*" everything from the cache, "/page/*" everything from the page-module (default render),
            - and "/page/view/*" only that specific subset of the page-module.
    """
    if prefix is None and key is None and kind is None:
        prefix = "/*"
    if prefix is not None:
        items = db.Query(CACHE_KINDNAME).filter("path =", prefix.rstrip("*")).iter()
        for item in items:
            db.delete(item)
        if prefix.endswith("*"):
            items = db.Query(CACHE_KINDNAME) \
                .filter("path >", prefix.rstrip("*")) \
                .filter("path <", prefix.rstrip("*") + u"\ufffd") \
                .iter()
            for item in items:
                db.delete(item)
        logging.debug(f"Flushing cache succeeded. Everything matching {prefix=} is gone.")
    if key is not None:
        items = db.Query(CACHE_KINDNAME).filter("accessedEntries =", key).iter()
        for item in items:
            logging.info(f"""Deleted cache entry {item["path"]!r}""")
            db.delete(item.key)
        if not isinstance(key, db.Key):
            key = db.Key.from_legacy_urlsafe(key)  # hopefully is a string
        items = db.Query(CACHE_KINDNAME).filter("accessedEntries =", key.kind).iter()
        for item in items:
            logging.info(f"""Deleted cache entry {item["path"]!r}""")
            db.delete(item.key)
    if kind is not None:
        items = db.Query(CACHE_KINDNAME).filter("accessedEntries =", kind).iter()
        for item in items:
            logging.info(f"""Deleted cache entry {item["path"]!r}""")
            db.delete(item.key)

