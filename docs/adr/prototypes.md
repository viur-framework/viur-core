---
covers: [viur.core.prototypes.skelmodule.SkelModule, viur.core.prototypes.list.List,
         viur.core.prototypes.tree.Tree, viur.core.prototypes.tree.TreeSkel,
         viur.core.prototypes.singleton.Singleton]
status: accepted
---
## Seam
`SkelModule` binds a module to a skeleton; `List` serves a flat kind, `Tree`
a node/leaf hierarchy (node-only when `leafSkelCls` stays None).

Skeleton selection - override the narrowest one that fits:
`_resolveSkelCls` -> `baseSkel` -> `viewSkel` / `addSkel` / `editSkel` /
`cloneSkel`. `skel(bones=..., exclude_bones=..., allow_client_defined=...)`
builds subskels for you.

Access control: `listFilter` (query rewriting, the only guard for `list()`)
and `canView` / `canAdd` / `canEdit` / `canDelete` / `canPreview` /
`canMove`.

Hooks: `onAdd`/`onAdded`, `onEdit`/`onEdited`, `onView`,
`onDelete`/`onDeleted`, `onClone`/`onCloned`, plus
`checkDeletePreconditions` for state (as opposed to permission) vetoes.
Sorting default: `default_order` (value or callable) - a dict goes through
`mergeExternalFilter`, so it is a default *filter*, not just an order.

## Rules
- To hide a field, remove the bone in `viewSkel`/`addSkel`/`editSkel` (or set
  it readOnly). Hiding it in a template protects nothing: the json/vi
  renderers still ship it and it stays filterable.
- `listFilter` must return None to deny, and `canView` has to agree with it -
  the default `canView` runs `listFilter` plus one extra query, which is the
  behaviour anything you override has to reproduce.
- Every `Tree` hook and permission function takes `skelType` as first
  parameter. Copying a `List` signature into a `Tree` breaks the call.
- A `Tree` subclass must set `nodeSkelCls` (assert in `__init__`).
- `add_or_edit` is importer-only: `@access("root")`, `@force_ssl`,
  `@force_post`, `@skey`.
- `canDelete` answers whether the *user* may delete,
  `checkDeletePreconditions` whether the *entry* may be deleted in its current
  state (default: refuse a `PreventDeletion` reference with `Locked`). Raise
  from the latter to veto.

## Traps
- The default `onAdded`/`onEdited`/`onDeleted`/`onCloned` call `flushCache`
  and write the audit log line. Overriding without `super()` silently disables
  cache invalidation.
- `Tree.onCloned` kicks off `_clone_recursive`, cloning the whole subtree in
  the background. Override without `super()` if that is not wanted.
- `default_order` is applied only when the query has no order yet, is not a
  multi-query, and no `search` parameter was sent.
- `skel(allow_client_defined=True)` evaluates the `X-VIUR-BONELIST` header and
  adds a `Vary` header. Without that header the flag is silently reset and you
  get the full skel; the `BadRequest` for a missing `"*"` subskel only fires
  when the header *is* present.
- `List.index()` takes its first argument as key *or* SEO key and answers with
  a 301 redirect when the request path is not the canonical SEO url.
- Deleting a `Tree` node is one deferred job that removes the whole subtree
  bottom-up and the node itself last, without spawning sub-tasks. Its
  `onDelete`/`onDeleted` fire exactly once, but from that job - not within the
  request. `deleteRecursive` validates the entire subtree up front, so a veto
  aborts before anything is deleted. Leafs are still deleted synchronously.
  `onDeleted`'s docstring warns that writing the skeleton again undoes the
  deletion.
- `edit`/`add`/`clone` only write on a POST request with data and without
  `bounce` - otherwise they render the skeleton, which looks like a success.

## Why not
`Tree.canAdd` receives the *parent node* skeleton, not the entry to be added:
the permission depends on the target repository/folder. `File.getUploadURL`
relies on exactly that.

## See also
[module](module.md), [skeleton](skeleton.md), [decorators](decorators.md),
[cache](cache.md), [modules/file](modules/file.md)
