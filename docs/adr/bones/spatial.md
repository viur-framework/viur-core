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
- `setBoneValue` guards with `if not isinstance(value, (tuple, list)) and
  len(value) == 2`. The `and` should be an `or`/`!=`: a 3-element tuple passes,
  a 2-character string raises. It also returns `None` instead of a bool.
- The tile index is written only when the bone *and* its parent are indexed.
  Switching `indexed` on later requires re-writing every entry.
- Values are validated against the bounds, so widening the region later is
  fine, narrowing it invalidates stored data.

## See also
[base](base.md), [../db/query](../db/query.md)
