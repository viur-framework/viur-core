---
covers: [viur.core.bones.boolean.BooleanBone]
status: accepted
---
## Seam
`BooleanBone` is tri-state: `True`, `False` and `None` for "not yet set".
Client values are parsed by `utils.parse.bool` against
`conf.bone_boolean_str2true` (default `("true", "yes", "1")`), so changing
that config changes what every BooleanBone accepts.

`buildDBFilter` parses the client's filter value the same way, so
`?flag=yes` filters correctly.

## Rules
- `multiple=True` is rejected in the constructor.
- `defaultValue` must be `True`, `False`, `None` or a callable - unless the
  bone has `languages`, where the complex structure is not validated at all.
- To keep the unset state, leave `defaultValue=None`; `getEmptyValue()` is
  `False`, so anything else collapses the tri-state.

## Traps
- `isEmpty(False)` is True. A deliberately stored `False` counts as empty, so
  a `required=True` BooleanBone can never be satisfied with "no".
- `setBoneValue` calls `utils.parse.bool(value)` **without**
  `conf.bone_boolean_str2true`, unlike every other path in this bone. With a
  project-specific truthy list the two disagree.
- `refresh` indexes `skel[name][lang]` for multi-language bones; when the
  value is still `None` that raises TypeError.
- `singleValueSerialize` keeps the value untouched when it equals
  `getEmptyValue()`, which is how an explicit `None` survives a write.

## See also
[base](base.md), [../config](../config.md)
