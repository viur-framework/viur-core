---
covers: [viur.core.cache.ResponseCache, viur.core.cache.flushCache, viur.core.cache.UserSensitive,
         viur.core.cache.DEFAULT_SETTINGS]
status: accepted
---
## Seam
`@ResponseCache(urls, renderer, user_sensitive, language_sensitive,
evaluated_args, max_cache_time, compression_level)` wraps an `@exposed` method
and serves the stored response from the `viur-cache` kind. 200 responses and
3xx redirects are cached; every argument omitted falls back to the global
`DEFAULT_SETTINGS`. A project-specific cache dimension can be added through
`conf.cache_environment_key`.

Invalidation is `flushCache(prefix=..., key=..., kind=...)`: the module
prototypes call it with `kind=` from `onAdded`/`onCloned` and with `key=` from
`onEdited`/`onDeleted`.

## Rules
- `evaluated_args` must list **every** parameter that influences the output.
  Unlisted parameters do not enter the key, so a cached response is served for
  a different request (the docstring names `order` as the classic mistake).
  Name `args` / `kwargs` there to include variadic parameters.
- `urls` restricts caching to the listed routes; `None` means "cache under
  every path". `renderer` restricts by render kind (`"html"`) or render class,
  standalone or in addition to `urls`.
- `user_sensitive` takes the `UserSensitive` enum
  (`IGNORE`/`GUEST_ONLY`/`BOTH`/`INDIVIDUAL`), not a number.
- To skip caching from project code, `conf.cache_environment_key` returns
  `BypassCache(reason)`. Raising `RuntimeError` still works but is deprecated.
- The response body is stored in the datastore entity, so it must be
  datastore-storable and stay below `MAX_PROPERTY_SIZE` (1 MiB - 89 bytes).
  `compression_level` compresses it beforehand;
  `DEFAULT_SETTINGS.raise_too_large` decides whether an oversized response
  raises or is returned uncached.
- `conf.debug.disable_cache` switches the cache off globally; users with `root`
  bypass it per request via the `X-Viur-Disable-Cache` header (evaluated in the
  router).

## Traps
- Invalidation only sees entities read with `db.get`/`put`/`delete` - the query
  part of the access log is commented out (`db/query.py`), so no kind ever
  reaches `accessedEntries`. `flushCache(kind=...)`, i.e. what `onAdded` and
  `onCloned` call, never matches anything, and a page that fetches its data
  through a query is never invalidated at all.
- `flushCache(key=...)` only derives a kind when `key` is *not* a `db.Key`
  (parsed with `Key.from_legacy_urlsafe`). The prototypes pass a real key, so
  no kind flush happens there.
- The size check uses `sys.getsizeof(body)`, which counts CPython's internal
  representation, not the UTF-8 bytes the datastore stores: 700k umlauts pass
  as "700 KB" and blow up in `db.Put` at 1.4 MB.
- `get_args` sets `__user`, `__lang`, `__path`, `__cache_environment`,
  `__app_version` and `__template_style` itself - an `evaluated_args` entry
  with one of these names is overwritten.
- A parameter that cannot be filled is silently dropped from the key (only a
  debug log), it no longer bypasses the cache.
- The key is built from `inspect.signature` of the *unwrapped* function;
  wrapping a `Method` replaces `Method._func` in place.
- `flushCache` is itself a `@CallDeferred` task, so invalidation is
  asynchronous. Right after a write the old response can still be served.
- `max_cache_time` does not delete anything, it only stops serving the entry.
- Not only `Content-Type` is restored: every `X-` header the wrapped function
  added, plus `Cache-Control`, is stored and replayed. The cache reports
  itself through `X-Cache-Status` (`HIT`/`MISS`/`UPDATED`/`BYPASS`/`TOO_LARGE`).
- `conf.db.create_access_log = False` does not disable caching - it only empties
  `accessedEntries`, so entries are cached and never invalidated.

## Why not
Cached responses live in the datastore instead of memcache: they survive
instance restarts, and invalidation can run as a query over `accessedEntries`,
which is exactly what `flushCache(key=...)` / `flushCache(kind=...)` do.

## See also
[prototypes](prototypes.md), [tasks](tasks.md), [db/query](db/query.md)
