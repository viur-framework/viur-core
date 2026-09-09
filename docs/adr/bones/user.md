---
covers: [viur.core.bones.user.UserBone]
status: accepted
---
## Seam
`UserBone` is a `RelationalBone` preconfigured for the `user` kind: `descr`,
`format` (`lastname, firstname (name)`) and
`refKeys=("key", "name", "firstname", "lastname")`.

Its own feature is the "magic": `creationMagic=True` stores the current user on
add, `updateMagic=True` on every write. Both are implemented in `performMagic`,
which `Skeleton.write` calls inside the write transaction, before serializing.

## Rules
- Magic and `multiple=True` are mutually exclusive (ValueError).
- With magic enabled the bone is forced to `readOnly=False` and defaults to
  `visible=False`. The forced `readOnly=False` also overrides an explicitly
  passed `readOnly=True`, so the *client* can write the bone unless you remove
  it from the add/edit skeleton.
- If no user is logged in, the magic sets the value to `None` - including on a
  write where the application set the value itself. Do not use it as proof of
  authorship.
- `refKeys` must keep `name`, `firstname` and `lastname` if `format` is left at
  its default; `RelationalBone` adds `key` and `shortkey` on its own.
- Prefer `compute` with `ComputeMethod.Once` / `OnWrite` over the magic - that
  is what `Skeleton.creationdate` / `changedate` do, and it implies
  `readOnly=True`.

## Traps
- `performMagic` is called for every write, so `updateMagic` overwrites a value
  set deliberately by application code in the same write.
- `structure()["type"]` is `relational.user`, but nothing tells the frontend
  that the value is written automatically: `creationMagic`/`updateMagic` are
  not exported and `readonly` is `False`, so it looks like an ordinary,
  editable relation.
- `creationMagic` only fires when `Skeleton.write` decides `is_add`, which is
  based on whether the entity existed in the datastore - not on whether the
  module called `add()`. `modules/formmailer.py` calls `performMagic` directly
  with `isAdd=True`, without any write at all.
- Resolving the current user is a datastore read (`db.get`) inside the write
  transaction. If the key does not resolve - user deleted, or a `kind` of its
  own, where `db.key_helper(..., adjust_kind=True)` rewrites the kind and keeps
  the id - `setBoneValue` returns False and the previous value silently stays.
  Both callers ignore the return value.
- `performMagic` is called with the skeleton, but its base signature names the
  first parameter `valuesCache`. The magic mechanism is marked deprecated at
  the call site (`skeleton/skeleton.py`); unlike `DateBone`, `UserBone` emits
  no DeprecationWarning.

## See also
[relational](relational.md), [base](base.md), [date](date.md),
[../skeleton](../skeleton.md)
