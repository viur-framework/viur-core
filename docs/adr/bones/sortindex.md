---
covers: [viur.core.bones.sortindex.SortIndexBone]
status: accepted
---
## Seam
`SortIndexBone` is a `NumericBone` preconfigured for manual ordering:
`precision=8`, `defaultValue` = current `time.time()`, and
`clone_behavior=SET_DEFAULT` so a cloned entry gets a fresh index instead of
the source's.

`TreeSkel.sortindex` is exactly this bone, and `Tree.default_order` is
`"sortindex"`. `Tree.move` writes `sortindex or time.time()`.

## Rules
- Keep `precision` high enough to insert between two neighbours. With
  `precision=0` new entries collide immediately.
- The bone is `readOnly=True` and `visible=False` in `TreeSkel`; reordering
  goes through `Tree.move` or an explicit `skel.patch()` (which passes
  `ignore=()` and therefore writes read-only bones), not through an edit form.
- Sorting by it requires the property to be indexed (it is, by default).

## Traps
- The default value is a timestamp, so "new entries sort last" only holds as
  long as nobody assigns smaller values by hand.
- `defaultValue` is a callable evaluated per skeleton instance; two entries
  created within the same float resolution can share an index, and the
  datastore then falls back to key order. `precision=8` does not help here -
  at timestamp magnitude the float64 step is already ~0.2 µs.
- `Tree.move` writes `sortindex or time.time()`, so `sortindex=0` is silently
  replaced by the current timestamp - an entry cannot be moved to index 0.
- `default_order` is skipped for multi-queries (`IN`/`OR` filters) and when the
  request carries a `search` kwarg, so a tree listing can come back in
  datastore order instead.

## See also
[numeric](numeric.md), [../prototypes](../prototypes.md)
