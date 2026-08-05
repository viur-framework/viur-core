---
covers: [viur.core.db.query.Query]
status: accepted
---
## Seam
`skel.all()` creates a `Query` with `srcSkel` set - only then are data-model
aware operations available (`mergeExternalFilter`, `fetch`, relational
filters). Bones hook into a query through their `buildDBFilter` /
`buildDBSort`, and may install `setFilterHook` / `setOrderHook` to rewrite
everything added afterwards. Fulltext search is delegated to
`DatabaseAdapter.fulltextSearch`.

## Rules
- Client input goes through `mergeExternalFilter` and nowhere else. It
  requires `srcSkel`, drops unknown keys, and clamps `limit` to
  `conf.db.query_external_limit` (negative limits become 0).
- `filter()` bypasses the data model completely - no bone ever sees the value.
  Use it only for values your own code produced.
- `count()` and `iter()` refuse multi-queries; `fetch()` requires `srcSkel`.
- Client-supplied cursors are safe by design (they cannot widen the filters) -
  documented on `setCursor`.

## Traps
- `queries is None` means "unsatisfiable". Every further `filter`/`order` call
  is a silent no-op and `run()` returns `[]`. A RuntimeError raised by a bone
  hook produces exactly this state, so an invalid relational filter looks like
  an empty result, not like an error.
- `!=` and `IN` expand into a list of `QueryDefinition`s. Merging,
  deduplication and re-sorting then happen in Python
  (`_merge_multi_query_results`), and `limit` applies per sub-query.
- An inequality filter implicitly prepends a sort order on that field.
- `iter()` deliberately ignores `limit()`.
- `getSkel()` fills and returns `srcSkel` itself - not a fresh instance.
  `fetch()` creates new instances but shares the `boneMap`.
- `_fixKind` silently returns the *parent* entities when the result kind
  differs from `origKind` - that is how relational queries on `viur-relations`
  get back to the source entities.
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
