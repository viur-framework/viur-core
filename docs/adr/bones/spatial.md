---
covers: [viur.core.bones.spatial.SpatialBone, viur.core.bones.spatial.haversine]
status: accepted
---
## Seam
`SpatialBone` stores a `(lat, lng)` tuple and, when indexed, a tile index that
makes "nearest to" queries possible. You must declare the searchable region up
front: `boundsLat`, `boundsLng`, `gridDimensions`. The grid size follows from
those (`getGridSize`).

A client filter `<bone>.lat` + `<bone>.lng` rewrites the query into four
sub-queries (north/south/east/west of the point) and installs
`_customMultiQueryMerge` / `_calculateInternalMultiQueryLimit`, which sort by
`haversine` distance and record how far the result is provably complete in
`query.customQueryInfo["spatialGuaranteedCorrectness"]`.

## Rules
- Keep the region as small as possible and the sub-regions roughly as wide as
  the largest distance you want to search - results further away than one tile
  are excluded at query level (class docstring).
- No boundary wrapping: a region crossing +/-180 degrees longitude, or "the
  whole world", does not work.
- Read `spatialGuaranteedCorrectness` before presenting results as complete.
- Not usable inside a relation: `buildDBFilter` asserts `prefix is None`.
- `indexed` and `multiple` together are rejected.
- `setBoneValue` takes a `(lat, lng)` tuple/list or a dict with `lat`/`lng`,
  and raises `ValueError` on anything else.

## Traps
- `getEmptyValue()` returns `(0.0, 0.0)` although its own docstring describes
  `(91.0, 181.0)`. If your region contains the origin, a legitimate `0, 0` is
  indistinguishable from "empty" - `isEmpty` reports True and the value is
  dropped.
- On an invalid or out-of-range client filter, `buildDBFilter` sets
  `dbFilter.datastoreQuery = None`. That attribute does not exist on
  `db.Query` (it is `queries`), so the query is **not** made unsatisfiable -
  it runs without the spatial constraint and returns everything the other
  filters allow.
- The filter is applied only when both `.lat` and `.lng` are present;
  supplying just one of them ignores it silently.
- `buildDBFilter` asserts that the query is not yet a multi-query. A list
  `key` filter, a `search` filter without a fulltext adapter, or a
  `RandomSliceBone` gets there first, and the resulting `AssertionError` is not
  caught by `db.Query.mergeExternalFilter` (it only catches `RuntimeError`).
- The bounds are each checked against +/-90 and +/-180, but not their order:
  a reversed tuple makes every value invalid. A `gridDimensions` entry of `0`
  raises `ZeroDivisionError` on the first write.
- The tile index is written only when the bone *and* its parent are indexed.
  Switching `indexed` on later requires re-writing every entry.
- Values are validated against the bounds, so widening the region later is
  fine, narrowing it invalidates stored data.

## See also
[base](base.md), [../db/query](../db/query.md)
