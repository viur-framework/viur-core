---
covers: [viur.core.bones.randomslice.RandomSliceBone]
status: accepted
---
## Seam
`RandomSliceBone` emulates `ORDER BY random()`. It stores a fresh random float
on every write (`serialize` ignores the current value) and, when the client
sorts by it (`orderby=<bone>`), rewrites the query into `2 * slices`
sub-queries around random centers, then merges them with
`customMultiQueryMerge` (dedupe, `sample`, `shuffle`).

Tuning: `slices` (number of centers, default 2) and `sliceSize` (how much of
the requested amount each sub-query fetches, default 0.5).

## Rules
- The bone must stay `visible=False` and `readOnly=True`; the constructor
  rejects anything else. It is always indexed.
- Sorting by it *changes which entries are returned*, not just their order -
  it is a sample, not a shuffle of the full result set.
- Not combinable with an `IN`/`!=` filter: `buildDBSort` asserts the query is
  not already a multi-query.
- Every write reshuffles that entry's position. Do not expect a stable order
  across requests, and do not use the value for anything else.

## Traps
- The constructor raises `NotImplemented`, not `NotImplementedError`. Since
  `NotImplemented` is not an exception, a visible or writable RandomSliceBone
  fails with `TypeError: exceptions must derive from BaseException` instead of
  the intended message.
- `buildDBSort` has the pre-`postfix` signature `(name, skel, dbFilter,
  rawFilter)`. It works because the only caller (`db.Query.mergeExternalFilter`)
  passes four positional arguments, but it breaks as soon as anything passes
  `postfix`.
- Despite its `-> Optional[db.Query]` annotation `buildDBSort` never returns
  anything; it rewrites `dbFilter` in place. The caller ignores the return
  value, but do not chain on it in your own code.
- `applyFilterHook` converts *any* exception from the query's filter hook into
  RuntimeError - including bugs in your own hook. `mergeExternalFilter` catches
  it, sets `queries = None` and the query silently returns nothing.
- The results are only sampled from `slices * 2 * ceil(amount * sliceSize)`
  fetched entries, so with a small `sliceSize` the sample is drawn from fewer
  entries than requested.

## See also
[base](base.md), [../db/query](../db/query.md)
