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
Defaults are `readOnly=True`, `visible=False`, `descr="Key"` and
`tags="technical"`.

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
- On read the `key` bone takes `skel.dbEntity.key` instead of a property of
  that name (and puts it into `accessedValues` like any other bone). A partial
  key - an entity that was never written - does not qualify, so it falls
  through to `BaseBone.unserialize` and `skel["key"]` ends up `None`.
- `serialize` for the `key` bone only writes when the name is in
  `accessedValues`, so `skel["key"]` must have been assigned.
- `check` and `isInvalid` only run for client input. `singleValueUnserialize`
  calls `singleValueFromClient(..., parse_only=True)`, which skips both - a
  stored key pointing at a deleted entity is never noticed on read.

## See also
[base](base.md), [../skeleton](../skeleton.md), [../db/query](../db/query.md),
[relational](relational.md)
