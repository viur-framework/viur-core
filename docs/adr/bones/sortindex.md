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
- The bone is `readOnly=True` in `TreeSkel`; reordering goes through
  `Tree.move` or an explicit `skel.patch()`, not through an edit form.
- Sorting by it requires the property to be indexed (it is, by default).

## Traps
- The default value is a timestamp, so "new entries sort last" only holds as
  long as nobody assigns smaller values by hand.
- `defaultValue` is a callable evaluated per skeleton instance; two entries
  created within the same float resolution can share an index, and the
  datastore then falls back to key order.

## See also
[numeric](numeric.md), [../prototypes](../prototypes.md)
