---
covers: [viur.core.bones.record.RecordBone]
status: accepted
---
## Seam
`RecordBone` embeds a whole `RelSkel` (the `using=` parameter) as the value of
one bone - a sub-form, optionally `multiple=True`. Reading yields a
`SkeletonInstance` of that RelSkel; the client sends subfields
(`parseSubfieldsFromClient` is True), so the wire format is
`<bone>.<index>.<subbone>`.

The bone forwards the bone protocol into the sub-skeleton:
`postSavedHandler`, `postDeletedHandler`, `getSearchTags`,
`getReferencedBlobs`, `refresh` all iterate the sub-bones. That is why a
`RelationalBone` or `FileBone` works inside a record.

## Rules
- `using` is required and must subclass `RelSkel`; `format` is required and
  `indexed` must stay False (NotImplementedError otherwise).
- Sub-bone relations are registered under the path
  `<bone>.<lang>.<index:02>.<subbone>` as `viur_src_property`. Do not
  reformat that path - `postSavedHandler` deletes stale relations by comparing
  it with a `>` filter.
- Entries beyond index 99 are not maintained: `postSavedHandler` logs
  "entry limit maximum reached" and stops cleaning up relations. Keep record
  lists shorter than 100 entries.
- `getUniquePropertyIndexValues` raises NotImplementedError - `unique=` is not
  available.

## Traps
- The index in the relation path is zero-padded to two digits, which is where
  the 99-entry limit comes from - reordering entries rewrites relations for
  every following index.
- `postSavedHandler` and `postDeletedHandler` iterate `value.items()` without
  the `if value is None: continue` guard that `getSearchTags` and
  `getReferencedBlobs` have. A `None` entry in a multiple record (a stored
  null) raises AttributeError during the write.
- `getSearchDocumentFields` calls `bone.getSearchDocumentFields`, which no
  longer exists on `BaseBone` - the method is dead and raises AttributeError
  if anything still calls it.
- `__init__` calls `issubclass(using, RelSkel)` before checking for `None`, so
  a missing `using` raises TypeError instead of the intended ValueError.
- `refresh` clears an entry by `setEntity(db.Entity())` when a nested relation
  demanded a cascade deletion - the record entry becomes falsy instead of
  being removed from the list.

## See also
[base](base.md), [relational](relational.md), [file](file.md),
[../skeleton](../skeleton.md)
