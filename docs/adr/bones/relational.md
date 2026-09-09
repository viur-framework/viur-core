---
covers: [viur.core.bones.relational.RelationalBone, viur.core.bones.relational.RelationalConsistency, viur.core.bones.relational.RelationalUpdateLevel, viur.core.skeleton.tasks.update_relations]
status: accepted
---
## Seam
Relations are read-optimized copies: the values named in `refKeys` are copied
from the target into the referencing entity, and a `viur-relations` entity is
written per reference. Extension points are `relskels_from_keys` /
`createRelSkelFromKey` (how a key becomes a reference), `refresh` (how a stale
copy is renewed), `getUniquePropertyIndexValues`, and the query rewriting hooks
`filterHook` / `orderHook`.

Configuration is the actual seam: `kind`, `module`, `refKeys`, `parentKeys`,
`using`, `updateLevel`, `consistency`, `format`.

## Rules
- Filter and sort only by bones listed in `refKeys` (`<bone>.dest.*`), in
  `using` (`<bone>.rel.*`) or in `parentKeys` (own properties). Anything else
  raises RuntimeError inside the bone, which `mergeExternalFilter` turns into
  an unsatisfiable query - not into an error the caller sees.
- `refKeys` always gains `key` and `shortkey`, `parentKeys` always gains `key`.
- Never `db.delete` an entity that is referenced with `PreventDeletion`. Use
  `skel.delete()`, otherwise the `viur-relations` entities go stale.
- Filtering a relation inside a query that is already a multi-query raises
  NotImplementedError in `_rewriteQuery`. The check is `isinstance(queries,
  list)`, so the trigger is any `IN`/`!=` filter in that query - including one
  on a completely different bone - although the message only mentions
  `multiple=True`.
- Leave `updateLevel` at `Always` for indexed bones. `update_relations`
  filters on `viur_relational_updateLevel = Always`, so copies of every other
  level are never renewed by the task at all.
- An unknown `kind` is only caught at startup: `setSystemInitialized` turns the
  `RefSkel.fromSkel` AssertionError into a NotImplementedError naming the
  skeleton, bone and kind.

## Traps
- Copies are refreshed by the deferred `update_relations` task, so a list
  filtered or sorted by a relational property serves stale data for a while -
  this is by design, not a bug.
- `refKeys` may contain fnmatch wildcards. The expanded names live in
  `_ref_keys` and are stored as `viur_foreign_keys`; iterating the raw patterns
  copies `None`.
- `CascadeDeletion` cascades transitively. `refresh` only sets
  `skel._cascade_deletion`; the deletion happens later in `Skeleton.write`,
  which deletes instead of writing.
- `consistency=Ignore` keeps a deleted target alive: `singleValueFromClient`
  re-uses the existing relation when the key no longer resolves.
- `relskels_from_keys` is all-or-nothing. One missing key returns an empty
  list, so `setBoneValue` fails for the whole list, not just that entry.
- `postSavedHandler` writes one `viur-relations` entity per referenced target.
  n:m relations multiply write operations on every save.
- `update_relations` filters `viur_foreign_keys IN changed_bones`; a changed
  bone that is not mirrored anywhere produces no update at all.
- Individual relations that cannot be updated are logged and skipped, not
  retried: an unknown `viur_src_kind` and a source entity that no longer
  exists both only produce a log line. Their copies stay stale forever.

## Why not
The implementation trades write cost for read cost on purpose (module
docstring). There is no write-efficient variant - do not "optimize" it by
dropping the mirrored values, queries and templates depend on them.

`parententry`/`parentrepo` in `TreeSkel` are `KeyBone`s, not RelationalBones
(marked TODO VIUR4). Tree hierarchy is therefore not covered by relational
consistency at all.

## See also
[bones/base](base.md), [skeleton](../skeleton.md), [tasks](../tasks.md),
[db/query](../db/query.md)
