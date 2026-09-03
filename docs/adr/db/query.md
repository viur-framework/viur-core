---
covers: [viur.core.db.query.Query]
status: accepted
---
## Seam
`skel.all()` creates a `Query` with `srcSkel` set - only then are data-model
aware operations available (`mergeExternalFilter`, `fetch`, relational
filters). Bones hook into a query through their `buildDBFilter` /
`buildDBSort`, and may install `setFilterHook` / `setOrderHook` to rewrite
everything added through `filter()` / `order()` afterwards - `or_filter()` is
not routed through them. Fulltext search is delegated to
`DatabaseAdapter.fulltextSearch`.

## Rules
- Client input goes through `mergeExternalFilter` and nowhere else. It
  requires `srcSkel`, drops unknown keys, and clamps `limit` to
  `conf.db.query_external_limit` (negative limits become 0).
- `filter()` bypasses the data model completely - no bone ever sees the value.
  Use it only for values your own code produced.
- `count()` and `iter()` refuse multi-queries; `fetch()` and `iter_skel()`
  require `srcSkel` and share the source skeleton's `boneMap`.
- `count()` returns `-1` on an unsatisfiable query, not `0`.
- `order()` resets the sort order from scratch on every call, `filter()`
  accumulates.
- Client-supplied cursors are safe by design (they cannot widen the filters) -
  documented on `setCursor`.

## Traps
- `queries is None` means "unsatisfiable": `filter`, `order`, `limit`,
  `distinctOn` and `or_filter` become silent no-ops and `run()` returns `[]`,
  but `setCursor` raises AssertionError, `getCursor` UnboundLocalError and
  `get_orders` ValueError. A RuntimeError raised by a bone hook produces this
  state, so an invalid relational filter looks like an empty result; every
  other exception from a hook escapes as an HTTP 500.
- A `search` filter without a suitable `customDatabaseAdapter` also sets this
  state - and `mergeExternalFilter` then still runs into `setCursor`.
- `IN` / `!=` / `NOT_IN` are native Datastore operators, not multi-queries.
  Only `KeyBone` (IN on a key list), `SpatialBone` and `RandomSliceBone` build
  a list of `QueryDefinition`s. `filter()` rejects a second such operator on
  the same field with a ValueError, but only while `queries` is not a list.
- Multi-query results are merged in Python (`_merge_multi_query_results`):
  `limit` applies per sub-query and the merged list is not trimmed, the
  implicit inequality sort order is dropped. Only a `_customMultiQueryMerge`
  reinstates a limit.
- A fulltext query runs once - `run()` clears `_fulltextQueryString`, so a
  second `run()` on the same query is a plain filter query. Unless the adapter
  sets `fulltextSearchGuaranteesQueryConstrains`, its result is filtered in
  Python against the filters and OR groups.
- An inequality filter implicitly prepends a sort order on that field.
- `iter()` deliberately ignores `limit()`.
- `getSkel()` fills and returns `srcSkel` itself - not a fresh instance.
  `fetch()` creates new instances but shares the `boneMap`.
- `_fixKind` decides on `resultList[0]` alone and then returns the *parent*
  entities - that is how relational queries on `viur-relations` get back to
  the source entities. They are deduplicated and keys that no longer exist are
  dropped, so the result can be shorter than the number of matches.
- `clone()` shares `customQueryInfo` with the original despite being
  documented as a deep copy.
- The access-log bookkeeping in `__init__` is commented out; only
  `db.current_db_access_log` writes from callers (e.g. `List.canView`) still
  feed cache invalidation.

## Why not
A query carries no access control. Restricting what a user may see is
`listFilter` in the module prototypes; a raw `db.Query` is unguarded, which is
why `mergeExternalFilter` must never be called on a query the module did not
create.

## See also
[skeleton](../skeleton.md), [bones/relational](../bones/relational.md),
[prototypes](../prototypes.md), [cache](../cache.md)
