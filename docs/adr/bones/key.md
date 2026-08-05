---
covers: [viur.core.bones.key.KeyBone]
status: accepted
---
## Seam
`KeyBone` stores a `db.Key`. It has two personalities: as the bone literally
named `key` it reads and writes `skel.dbEntity.key` itself; under any other
name it behaves like a normal bone storing a key property (that is how
`TreeSkel.parententry` / `parentrepo` work).

Configuration: `allowed_kinds` (restrict and adjust the kind via
`db.key_helper`), `check=True` (verify the entity exists on read-from-client).
Defaults are `readOnly=True`, `visible=False`.

## Rules
- Keep the `key` bone read-only. `Skeleton.key` carries a comment saying so:
  a writable key bone lets a client choose the entity it overwrites through
  add/edit.
- `allowed_kinds` is the whitelist. Without it any parseable key of any kind
  is accepted.
- `check=True` costs one `db.get` per submitted value and does not make the
  reference transactional - the entity can vanish afterwards.

## Traps
- `singleValueFromClient` parses with `db.normalize_key` (or `key_helper`),
  while `buildDBFilter` decodes with `db.Key.from_legacy_urlsafe` only.
  Filtering by a key notation that the bone happily *stores* can therefore
  raise RuntimeError, which `mergeExternalFilter` converts into an empty
  result set.
- `buildDBFilter` returns `None` when the bone is not part of the filter,
  instead of the query. Callers in viur-core ignore the return value; your own
  code must not chain on it.
- For `name == "key"` the filter is rewritten to `__key__`, so the client
  filter `key=` never hits a property named `key`.
- `singleValueUnserialize` raises ValueError for a stored value it cannot
  parse - a corrupt key breaks reading the whole skeleton, it is not skipped.
- The `key` bone bypasses `accessedValues` bookkeeping on read (it takes
  `dbEntity.key` directly) but requires `accessedValues` on write, so
  `skel["key"]` must be assigned for `serialize` to do anything.

## See also
[base](base.md), [../skeleton](../skeleton.md), [../db/query](../db/query.md),
[relational](relational.md)
