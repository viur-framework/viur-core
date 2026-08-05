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
interval=ComputeMethod.Once)` plus `unique=UniqueValue(SameValue, ...)`.
Replace `generate_fn` to change the format entirely; it receives `skel` and
`bone`.

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
- `generate_number` retries a `CollisionError` three times *inside* the
  transaction body, with `time.sleep(i + 1)` - a sleep inside a datastore
  transaction. Under contention this blocks the request instead of failing
  fast.
- The counter entity is not deleted with the entries. Deleting all entries
  does not reset the numbering.
- `length` only matters when padding; a number longer than
  `length - len(pattern)` is not truncated, it just gets longer.

## See also
[base](base.md), [../skeleton](../skeleton.md)
