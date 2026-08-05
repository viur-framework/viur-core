---
covers: [viur.core.bones.color.ColorBone]
status: accepted
---
## Seam
`ColorBone` stores a hex color string. `mode="rgb"` (default) accepts 3- and
6-digit values, `mode="rgba"` accepts 8 digits; a missing `#` is added and the
3-digit shorthand is expanded. Validation is character-based (hex digits plus
one `#`).

For anything else - named colors, `rgb()` notation, alpha as a separate
value - use a `StringBone` with a `vfunc`, not this bone.

## Rules
- `mode` must be `"rgb"` or `"rgba"` (assert).
- The value is stored lower-case with a leading `#`.
- `mode="rgba"` does not accept 3- or 6-digit values - switching the mode of
  an existing bone invalidates the stored values.

## Traps
- The length checks cascade: a 3-character input is first prefixed to 4
  characters and then expanded by the 4-character branch. A value like `#ab`
  (one `#`, hex digits, length 3) survives that chain and is stored as
  `###aabb`. Do not rely on the bone rejecting malformed short values.
- `getEmptyValue()` is inherited from `BaseBone`, i.e. `None`, so an empty
  color and an unset color are the same thing.

## See also
[base](base.md), [string](string.md)
