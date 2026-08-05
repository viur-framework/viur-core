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
  classes do not guess the tree module for you.

## Traps
- `type` is the only difference, so nothing enforces that the referenced kind
  actually is a node or a leaf of a tree. A `TreeNodeBone` pointing at a leaf
  kind fails in the admin tool, not on write.

## See also
[relational](relational.md), [file](file.md),
[../prototypes](../prototypes.md)
