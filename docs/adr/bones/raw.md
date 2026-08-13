---
covers: [viur.core.bones.raw.RawBone]
status: accepted
---
## Seam
`RawBone` is the "no processing at all" bone and the base of `StringBone`,
`TextBone` and `JsonBone`. Its only own logic is `singleValueFromClient`
(pass the value through, run `isInvalid`) and a `getSearchTags` that splits on
whitespace.

Subtype it via `type_suffix` (`"raw.code.markdown"`) rather than a new class
when only the frontend behaviour differs.

## Rules
- Do not use `RawBone` for client-supplied data unless something else
  validates or strips it. Its own docstring warns about reflected XSS - the
  value reaches templates and JSON exactly as it was sent.
- If you need HTML, use `TextBone` (sanitizing); if you need plain text, use
  `StringBone` (escaping). `RawBone` is for values a *trusted* source produced.

## Traps
- `isInvalid` is inherited from `BaseBone` and returns `False`, so a plain
  `RawBone` accepts everything. Validation only exists if you pass `vfunc`.
- On a validation error `singleValueFromClient` returns the *original* value
  instead of `getEmptyValue()`, unlike every other bone. `fromClient` assigns
  it regardless of the errors, so after a failed `vfunc` the rejected value
  still sits in `skel[name]`.
- `getSearchTags` puts the raw words into `viurTags`, so raw content lands in
  the search index even though it was never sanitized. This only happens for
  `searchable=True` bones - the adapter checks that before calling - and tags
  longer than the adapter's `max_length` are dropped.
- The tags are built from `str(value)`, so subclasses holding non-string
  values (a `JsonBone`) index the Python representation of the structure,
  braces and quotes included.

## See also
[base](base.md), [string](string.md), [text](text.md), [json](json.md)
