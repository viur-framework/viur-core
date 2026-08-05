---
covers: [viur.core.cache.enableCache, viur.core.cache.flushCache, viur.core.cache.keyFromArgs]
status: accepted
---
## Seam
`@enableCache(urls, userSensitive, languageSensitive, evaluatedArgs,
maxCacheTime)` wraps an `@exposed` method and serves the stored response from
the `viur-cache` kind. Invalidation is `flushCache(prefix=..., key=...,
kind=...)`, which the module prototypes already call from
`onAdded`/`onEdited`/`onDeleted`/`onCloned`. A project-specific cache
dimension can be added through `conf.cache_environment_key`.

## Rules
- `evaluatedArgs` must list **every** parameter that influences the output.
  Unlisted parameters do not enter the key, so a cached response is served for
  a different request (the docstring names `order` as the classic mistake).
- `urls` must contain each url the function is reachable under, and only those
  which may be cached (the docstring's example: cache `/page/view`, not
  `/admin/page/view`).
- Requires `conf.db.create_access_log = True`; without it caching is disabled
  with a warning, because invalidation relies on the recorded data access.
- Only the `Content-Type` header is stored and restored. Do not cache
  functions that set other headers or depend on the environment.
- `evaluatedArgs` entries must not start with `_` (assert).

## Traps
- `keyFromArgs` returns None - meaning "no caching", silently - when
  `userSensitive == 1` and a user is logged in, when
  `conf.cache_environment_key` raises RuntimeError, or when not every
  positional parameter of the function could be filled.
- The key is built from `f.__code__`/`f.__defaults__` of the *unwrapped*
  function; wrapping a `Method` replaces `Method._func` in place.
- `flushCache` is itself a `@CallDeferred` task, so invalidation is
  asynchronous. Right after a write the old response can still be served.
- `flushCache(key=...)` also drops entries that merely queried the *kind* of
  that key; a non-`db.Key` value is parsed with `Key.from_legacy_urlsafe`.
- `maxCacheTime` does not delete anything, it only stops serving the entry.
- Users with `root` bypass the cache per request via the
  `X-Viur-Disable-Cache` header (evaluated in the router).
- The response body is stored in the datastore entity, so it must be
  datastore-storable and stay below the entity size limit.

## Why not
Cached responses live in the datastore instead of memcache: they survive
instance restarts, and invalidation can run as a query over `accessedEntries`,
which is exactly what `flushCache(key=...)` / `flushCache(kind=...)` do.

## See also
[prototypes](prototypes.md), [tasks](tasks.md), [db/query](db/query.md)
