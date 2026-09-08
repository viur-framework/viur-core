---
covers: [viur.core.bones.color.ColorBone]
status: accepted
---
## Seam
`ColorBone` stores a hex color string. `mode="rgb"` (default) accepts 3- and
6-digit values, `mode="rgba"` accepts 8 digits (`VALID_LENGTHS`); a missing
`#` is added and the 3-digit shorthand is expanded. Input is normalized in
this order: type check, lower-case, strip an optional leading `#`, reject any
non-hex character, reject a length the mode does not allow, expand the
shorthand, prefix `#`.

For anything else - named colors, `rgb()` notation, alpha as a separate
value - use a `StringBone` with a `vfunc`, not this bone.

## Rules
- `mode` must be a key of `VALID_LENGTHS` (`"rgb"` or `"rgba"`), ValueError
  otherwise.
- The value is stored lower-case with exactly one leading `#`, and that is the
  only position a `#` may appear in the input.
- `mode="rgba"` does not accept 3- or 6-digit values - switching the mode of
  an existing bone invalidates the stored values.

## Traps
- `getEmptyValue()` is inherited from `BaseBone`, i.e. `None`, so an empty
  color and an unset color are the same thing.
- `singleValueFromClient` ends with `self.isInvalid(value)`, so an override of
  `isInvalid` sees the already normalized `#rrggbb` form, never the raw input.

## See also
[base](base.md), [string](string.md)
