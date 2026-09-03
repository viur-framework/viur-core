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
- `multiple=True` is rejected in the constructor with a ValueError, an invalid
  `defaultValue` with a TypeError (the class docstring claims ValueError for
  both).
- `defaultValue` must be `True`, `False`, `None` or a callable - unless the
  bone has `languages`, where the complex structure is not validated at all.
- To keep the unset state, leave `defaultValue=None`; `getEmptyValue()` is
  `False`, so anything else collapses the tri-state.
- `setBoneValue` raises ValueError on `append=True` and returns False for a
  language this bone does not have.

## Traps
- The tri-state does not survive a write. `singleValueSerialize` only keeps a
  value that equals `getEmptyValue()` (= `False`), and `None == False` is
  False, so `None` falls through to `utils.parse.bool(None)` and is stored as
  `False`. Only a bone whose `getEmptyValueFunc` returns `None` keeps the
  unset state - that is the case the code comment is about.
- `isEmpty(False)` is True, so a `required=True` bone rejects a real boolean
  `False` (as sent by a JSON client) as "empty". Form-style strings escape
  this: `isEmpty` sees the raw client value, and `"false"`, `"0"` or `"no"`
  are non-empty strings that are then parsed to `False` and accepted.
- `setBoneValue` calls `utils.parse.bool(value)` **without**
  `conf.bone_boolean_str2true`, unlike every other path in this bone. With a
  project-specific truthy list the two disagree.
- `refresh` indexes `skel[name][lang]` for multi-language bones; when the
  value is still `None` that raises TypeError.

## See also
[base](base.md), [../config](../config.md)
