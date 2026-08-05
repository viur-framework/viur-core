---
covers: [viur.core.bones.user.UserBone]
status: accepted
---
## Seam
`UserBone` is a `RelationalBone` preconfigured for the `user` kind: `descr`,
`format` (`lastname, firstname (name)`) and
`refKeys=("key", "name", "firstname", "lastname")`.

Its own feature is the "magic": `creationMagic=True` stores the current user on
add, `updateMagic=True` on every write. Both are implemented in
`performMagic`, which `Skeleton.write` calls before serializing.

## Rules
- Magic and `multiple=True` are mutually exclusive (ValueError).
- With magic enabled the bone is forced to `readOnly=False` and defaults to
  `visible=False` - it has to be writable for `setBoneValue` to work inside
  `performMagic`, which means the *client* can write it too unless you remove
  the bone from the add/edit skeleton.
- If no user is logged in, the magic sets the value to `None`. Do not use it as
  proof of authorship.
- `refKeys` must keep `name` if `format` is left at its default.

## Traps
- `performMagic` is called for every write, so `updateMagic` overwrites a value
  set deliberately by application code in the same write.
- The bone has no own `type`, so it is a plain `relational` for the frontend -
  no user-specific widget.
- `creationMagic` only fires when `Skeleton.write` decides `is_add`, which is
  based on whether the entity existed in the datastore - not on whether the
  module called `add()`.
- `performMagic` is called with the skeleton, but its base signature names the
  first parameter `valuesCache`; the module docstring of `base` marks the whole
  magic mechanism as deprecated for VIUR4.

## See also
[relational](relational.md), [base](base.md), [../skeleton](../skeleton.md)
