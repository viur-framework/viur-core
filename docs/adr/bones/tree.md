---
covers: [viur.core.bones.treeleaf.TreeLeafBone, viur.core.bones.treenode.TreeNodeBone]
status: accepted
---
## Seam
`TreeLeafBone` and `TreeNodeBone` are `RelationalBone`s that carry no own
logic - they exist purely to set `type` to `relational.tree.leaf` respectively
`relational.tree.node`, which tells the admin tool to offer a tree selector for
the referenced module instead of a flat list.

Use `TreeNodeBone` to reference a node (folder) and `TreeLeafBone` to reference
a leaf. `FileBone` is the one relevant subclass of `TreeLeafBone`.

They are documented together because there is nothing to say about either one
that is not identical; everything else lives in
[relational](relational.md).

## Rules
- Pick the class by what the *target* is (node or leaf), not by where the bone
  sits. Referencing a `Tree` module's leaves with a plain `RelationalBone`
  works at the datastore level but gives the wrong frontend widget.
- `kind` and `module` still have to be set as for any relational bone - these
  classes do not guess the tree module for you. In a tree module the node and
  leaf kindNames rarely match the module name (`kind="viur-script-leaf"` with
  `module="script"` in `modules/moduleconf.py`).

## Traps
- `type` is the only difference, so nothing enforces that the referenced kind
  actually is a node or a leaf of a tree. Picking the wrong class only shows as
  the wrong list in the admin tool.
- `module` is not enforced: `RelationalBone.__init__` falls back to `kind` when
  `module` is omitted. For a tree module that fallback is almost always wrong
  and stays silent - the admin tool then queries a module that does not exist.
- `structure()` reports `type` with `kind` appended, so the frontend sees
  `relational.tree.leaf.file.file` for a `FileBone`, not `type` verbatim.
- A key of a foreign kind is not rejected: `relskels_from_keys` resolves with
  `db.key_helper(..., adjust_kind=True)`, which rewrites the kind and keeps the
  id (intentional since #1417). Handing a node key to a leaf bone therefore
  fails as an ordinary validation error on save - or silently links whatever
  entity carries that id in the bone's kind.

## See also
[relational](relational.md), [file](file.md),
[../prototypes](../prototypes.md)
