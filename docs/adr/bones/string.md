---
covers: [viur.core.bones.string.StringBone]
status: accepted
---
## Seam
`StringBone` (a `RawBone`) adds length limits, HTML escaping, case-insensitive
matching and natural sorting. Hooks worth knowing:

- `type_coerce_single_value` - how non-str values become str; override it to
  accept your own types.
- `natural_sorting` - pass a callable to build your own sort index, or `True`
  for the built-in DIN 5007 variant 2 transformation.
- `v_func_valid_chars(charset)` - ready-made `vfunc` factory for charset
  restrictions.

## Rules
- `escape_html=False` means the value is stored unescaped. Then the renderer
  and every template are responsible - the same warning as for
  [raw](raw.md) applies.
- `caseSensitive=False` or `natural_sorting` change the *stored layout*: the
  value becomes a dict `{"val": ..., "idx": ..., "sort_idx": ...}` when the
  parent is indexed. Filtering and sorting then run on the sub-properties, so
  changing either flag on an existing kind requires re-writing every entry
  (`refresh`) plus new datastore indexes.
- `max_length` defaults to 254 and is enforced in `isInvalid` *and* by
  truncation in `singleValueFromClient`.

## Traps
- With `escape_html=True` the value is escaped *and* truncated to
  `max_length` by `utils.string.escape` - the escaped form is what is counted,
  so an input of legal length can still lose characters.
- `singleValueUnserialize` reads the `"val"` sub-property, but a value stored
  while `caseSensitive=False` and read while it is `True` (or vice versa) is
  handled silently - `idx`/`sort_idx` then simply go stale.
- `getUniquePropertyIndexValues` raises NotImplementedError for
  multi-language bones. A `unique=` + `languages=` StringBone therefore only
  fails at write time.
- `natural_sorting` is an instance attribute *and* a method: passing `False`
  sets it to `None`, passing `True` leaves the method in place. Do not test it
  with `callable()` to find out whether it is enabled.
- The built-in `natural_sorting` maps `ẞ` (capital) but not `ß`, so lowercase
  sharp s is not folded to `ss`.
- `isInvalid` calls `len(value)` without a type check; a non-str reaching it
  directly (not through `singleValueFromClient`) raises TypeError.

## See also
[raw](raw.md), [base](base.md), [text](text.md), [credential](credential.md),
[email](email.md), [phone](phone.md), [password](password.md)
