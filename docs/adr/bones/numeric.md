---
covers: [viur.core.bones.numeric.NumericBone]
status: accepted
---
## Seam
`NumericBone` stores int or float, decided by `precision`: `precision=0` casts
to `int`, anything else rounds to that many decimal places. `min`/`max` bound
the accepted range (defaults `MIN`/`MAX` = the platform's `sys.maxsize`
window, which is also the datastore's 8-byte limit).

`_convert_to_numeric` is the conversion point for the int/float mode - it also
unpacks a `{"val": ...}` dict, so a bone migrated from `StringBone` keeps
working. `refresh` re-runs that conversion over stored values.

`decimal=True` switches the bone to `decimal.Decimal` for exact arithmetic,
with `_convert_to_decimal` as its own conversion point (quantized to
`precision`, float values via a `str()` roundtrip). It is a different storage
format: `singleValueSerialize` writes
`{"val": <float>, "decimal": "<str>"}`, and `buildDBFilter` therefore filters
on the `<name>.val` sub-property.

## Rules
- Comma is accepted as decimal separator (first occurrence only) both from
  clients and in `_convert_to_numeric`.
- Limits are checked *after* rounding, because rounding can move a value
  across the bound.
- `min`/`max` outside the `MIN`/`MAX` window raise ValueError - the guard sits
  in `__setattr__`, so it also fires on later assignment.
- Changing `precision` on an existing kind changes the stored type. Run a
  `refresh` over the kind afterwards.
- The same holds for `decimal`, and harder: it changes a scalar property into
  a `{"val", "decimal"}` entity. Reading old scalar values still works, but
  queries do not - see Traps.
- `_quantize_exp` only exists when `decimal=True`; everything reaching for it
  must go through the `self.decimal` branch first.

## Traps
- With `precision=0` a float input is rejected by `int(value)` - but
  `_convert_to_numeric` (used by `refresh` and `unserialize`) goes through
  `int(float(value))` and silently truncates. Client input and refresh
  therefore disagree on `"42.5"`.
- `singleValueUnserialize` falls back to `getDefaultValue(None)` on garbage.
  With a callable `defaultValue` that call fails - the FIXME in the code says
  as much.
- `isEmpty` returns True for anything unconvertible, so invalid input is
  swallowed as "empty" before `singleValueFromClient` ever runs.
- `getEmptyValue()` is `0` / `0.0`, and `isEmpty(0)` is True. A legitimately
  entered zero is treated as empty and, in multiple bones, dropped during
  serialization.
- `iter_bone_value` is overridden to keep falsy numbers - do not "simplify" it
  back to the base implementation.
- A float bone with `multiple=True` is not blocked here although the
  `__setattr__` docstring claims it is.
- After switching a bone to `decimal=True`, filters target `<name>.val` while
  existing entries still hold a scalar. Those entries silently stop matching
  any query on this bone until they are rewritten or refreshed.
- Filtering in decimal mode goes through `float()` and compares against the
  stored `val` float, so the exactness the mode exists for does not apply to
  queries - only to the value handed back to the application.

## See also
[base](base.md), [sortindex](sortindex.md), [spam](spam.md),
[string](string.md)
