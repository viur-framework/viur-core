---
covers: [viur.core.skeleton.skeleton.Skeleton, viur.core.skeleton.base.BaseSkeleton,
         viur.core.skeleton.relskel.RelSkel, viur.core.skeleton.relskel.RefSkel,
         viur.core.skeleton.instance.SkeletonInstance, viur.core.skeleton.meta.MetaSkel,
         viur.core.skeleton.meta.MetaBaseSkel, viur.core.skeleton.skeleton.SeoKeyBone,
         viur.core.skeleton.adapter.DatabaseAdapter,
         viur.core.skeleton.adapter.ViurTagsSearchAdapter,
         viur.core.skeleton.utils.skeletonByKind,
         viur.core.skeleton.utils.without_render_preparation]
status: accepted
---
## Seam
Data model: subclass `Skeleton` inside a folder listed in
`conf.skeleton_search_path`. `kindName` is derived from the class name
(trailing `Skel` stripped, lower-cased) for everything outside `viur.core`.
A shared base without its own kind gets the class-name suffix `AbstractSkel`.
Remove an inherited bone by assigning `None` to its name.

Per-skeleton hooks (all classmethods taking `skel` first):
`preProcessSerializedData`, `preProcessBlobLocks`, `postSavedHandler`,
`postDeletedHandler`, `getCurrentSEOKeys`, `refresh`, plus the list
`interBoneValidations`.

Database-side hooks: assign `database_adapters` (one or many
`DatabaseAdapter`), which gets `prewrite` / `write` / `delete` and optionally
`fulltextSearch`. Without an explicit setting `ViurTagsSearchAdapter` is
attached automatically.

`RelSkel` is a bone container without a kind (used for `using=` and task data
skeletons); `RefSkel.fromSkel(kind, *patterns)` builds the reduced skeleton a
`RelationalBone` mirrors, and `RefSkel.read()` loads the full entity from it -
or a subskel of it, with `subskel=` / `bones=`.

## Rules
- Bone names may contain only letters, digits and `_`, and must not be one of
  the reserved keywords (`read`, `write`, `patch`, `delete`, `clone`, `errors`,
  `structure`, ... - see `MetaBaseSkel.__reserved_keywords`).
- Two skeletons for the same kind in the same `conf.skeleton_search_path`
  entry raise ValueError; across entries the lower index wins silently. A
  skeleton in a folder that is not listed at all raises NotImplementedError.
- Do not modify values while rendering: `read`, `write`, `fromClient` and
  `__setitem__` assert `skel.renderPreparation is None`. Use
  `without_render_preparation()` when a template needs raw values.
- Overriding `fromDB`/`toDB` still works, but is deprecated; `read`/`write`
  dispatch to them when they exist in the subclass `__dict__`.
- `skel.delete()` re-instantiates the full skeleton via `skeletonByKind`, so
  never rely on a subskel's bones being the ones that run the delete hooks.

## Traps
- `Skeleton()` returns a `SkeletonInstance`, not an instance of your class.
  Class attributes and `@property` are reached through
  `SkeletonInstance.__getattr__`; a `@property` always sees raw values.
- `write()` runs in a transaction, re-reads the entity into a fresh instance
  and moves `accessedValues` over. The bones' `postSavedHandler` and the
  adapters' `write` run *outside* that transaction.
- A taken unique value raises a plain `ValueError` from `write()`, while
  `fromClient()` only reports a `ReadFromClientError`. The race between both
  therefore surfaces as a 500.
- `patch()` defaults to `internal=True` (swallows NotSet/Empty errors) and
  `ignore=()`, which means read-only bones *are* writable through it.
- `read(create=...)` writes the entity immediately.
- SEO keys: a colliding key gets a random suffix, three attempts, then
  ValueError; `viurActiveSeoKeys` is trimmed to the last 200 entries.
- `boneMap` is shared with the class unless `clone=True` - mutating a bone on
  an uncloned instance changes it for every skeleton of that kind.
- `RefSkel.read()` raises ValueError when the target is gone; it does not
  return None.
- `ViurTagsSearchAdapter` writes `viurTags` in `prewrite`, so a fulltext hit
  depends on the last write, not on the current values.

## Why not
`SkeletonInstance` exists instead of real class instances for speed (its
docstring) - which is why every hook is a classmethod with an explicit `skel`
parameter instead of using `self`.

## See also
[bones/base](bones/base.md), [bones/relational](bones/relational.md),
[db/query](db/query.md), [prototypes](prototypes.md), [tasks](tasks.md)
