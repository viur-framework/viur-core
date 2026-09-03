---
covers: [viur.core.bones.base.BaseBone, viur.core.bones.base.Compute, viur.core.bones.base.ReadFromClientError, viur.core.bones.base.setSystemInitialized]
status: accepted
---
## Seam
Own bone type: subclass `viur.core.bones.base.BaseBone` and override the
single-value layer - `singleValueFromClient`, `singleValueSerialize`,
`singleValueUnserialize`, `structure`, `_atomic_dump`. Multiplicity,
languages and compute handling live in `fromClient` / `serialize` /
`unserialize` and are not your business.

One-off customization without a subclass: `vfunc` (validation), `isEmptyFunc`,
`getEmptyValueFunc`, `type_suffix` (frontend type variant), `params`, `tags`.

Post-processing the client value: `after_from_client(skel, name, errors)` runs
at the end of `fromClient`, after `skel[name]` was written and all validation
incl. the multiple-constraints has run. Normalize the value in place or
add/remove entries from `errors` there instead of wrapping `fromClient`.

Side effects around the write: `postSavedHandler`, `postDeletedHandler`,
`delete` (runs inside the write transaction), `refresh`,
`getReferencedBlobs`, `getSearchTags`, `getUniquePropertyIndexValues`.

Caches that need other skeletons to exist belong into `setSystemInitialized`.
At startup `viur.core.bones.base.setSystemInitialized` walks all skeleton
classes and each `Skeleton.setSystemInitialized` calls it on its bones.

## Rules
- Never override `fromClient`/`serialize`/`unserialize` to convert a value.
  They implement the multiple/languages/compute matrix; a partial
  re-implementation loses one of those cases.
- `isEmpty` takes precedence over `isInvalid`, and it receives untrusted
  client input as well as stored values. It must not raise.
- `compute=` only works with `readOnly=True`. When `readOnly` is not passed at
  all it is set for you; passing `readOnly=False` raises.
- `buildDBFilter` / `buildDBSort` get the raw client filter dict. Ignore every
  key that is not yours and never trust the values.
- `BaseBone.singleValueFromClient` refuses everything by design - a subclass
  without its own implementation cannot read client data at all.
- `tags` classifies the data content (`"personal"`, `"contact"`, ... ) for
  privacy tooling, audits and anonymization. It is exported in `structure()`
  and is explicitly not an access-control mechanism.

## Traps
- After startup bones are frozen: `__setattr__` raises unless the instance is
  cloned (`skel.ensure_is_cloned()` / `subskel(clone=True)`). Names starting
  with `_` bypass the guard - that is how `_prevent_compute` works.
- `serialize` writes only when the bone name is in `skel.accessedValues` (or
  the bone is computed). Touching `skel.dbEntity` directly is invisible to it.
- `_compute` sets `skel.accessedValues[bone] = None` before calling
  `compute.fn` to break recursion, so a compute function reading its own bone
  sees `None`. This only happens when `compute.fn` declares a `skel` parameter.
- `ComputeMethod.Lifetime` writes to the datastore from `unserialize`, in its
  own transaction if none is open. Reading a skeleton can be a write.
- Values equal to `getEmptyValue()` are dropped while serializing a multiple
  bone (with or without languages), so empty slots never reach the datastore.
  A language bone that is not multiple stores its empty values.
- `after_from_client` is not called on the `NotSet` early-return, i.e. when the
  field was absent from the request. It is the one path where the hook is
  silently skipped.
- `structure()["required"]` is `required and not readOnly` - a readOnly bone
  never looks required to the frontend, whatever you configured.

## Why not
`clone_behavior` defaults to `SET_DEFAULT` for `unique` + `readOnly` bones and
to `COPY_VALUE` otherwise: a cloned entry must not carry a value whose unique
lock belongs to the source entry.

`performMagic` still exists and is still called from `Skeleton.write`, but is
marked deprecated there. Use `compute` or a hook instead.

## See also
[bones/relational](relational.md), [skeleton](../skeleton.md),
[db/query](../db/query.md)
