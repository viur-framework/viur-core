---
covers: [viur.core.bones.uid.UidBone, viur.core.bones.uid.generate_uid, viur.core.bones.uid.generate_number]
status: accepted
---
## Seam
`UidBone` produces a gap-free running number per skeleton and bone, formatted
into a `pattern` where `*` is replaced. The counter lives in the datastore kind
`viur-uids` under the key `<kindName>-<boneName>-uid` and is incremented in a
transaction (`generate_number`).

The bone wires itself up as `compute=Compute(fn=generate_fn,
interval=ComputeInterval(ComputeMethod.Once))` plus
`unique=UniqueValue(SameValue, ...)`. Replace `generate_fn` to change the
format entirely; `_compute` injects the parameters it declares (`skel`, `bone`,
`bone_name`).

## Rules
- The bone must be `readOnly=True` (ValueError otherwise) and cannot be
  `multiple` or translated.
- `pattern` must contain exactly one `*`; `fillchar` must be exactly one
  character.
- Because the value is computed `Once`, it is assigned on the first write and
  never recalculated. Never edit it afterwards - the unique lock belongs to it.
- Two bones sharing a counter means sharing the same `<kind>-<bone>-uid` key;
  the counter is per skeleton *and* bone name, so renaming the bone restarts
  the numbering.

## Traps
- `fillchar` defaults to `"*"`, so the default padding character is an
  asterisk (`"***********0"`), not a zero. Pass `fillchar="0"` if you want
  leading zeros.
- The first generated number is `0`: an entity is created with `count = 0` and
  that value is returned.
- Padding cannot be switched off. `fillchar` must be exactly one character, so
  `if bone.fillchar` in `generate_uid` is always true and its unpadded branch
  is dead code. Set `length <= len(pattern)` instead.
- `generate_number` catches `db.CollisionError`, which no longer exists since
  the datastore re-integration (#1431). Any exception raised in the retry body
  is masked by an `AttributeError`; the retry never runs, the `time.sleep` is
  never reached and `ValueError("Can't set the Uid")` is unreachable.
- `serialize_compute` runs inside the skeleton's write transaction, so
  `generate_number` joins that transaction instead of opening its own. The
  counter entity is therefore read and written on every add of that kind, which
  serialises entity creation; on conflict `run_in_transaction` retries three
  times (sleeping 1/2/4 s) and then raises `RuntimeError`.
- `unserialize_compute` has no branch for `ComputeMethod.Once`, so the number
  is only ever produced on write - never on read.
- The counter entity is not deleted with the entries. Deleting all entries
  does not reset the numbering.
- `length` only matters when padding; a number longer than
  `length - len(pattern)` is not truncated, it just gets longer.

## See also
[base](base.md), [../skeleton](../skeleton.md)
