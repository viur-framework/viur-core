---
covers: [viur.core.bones.json.JsonBone]
status: accepted
---
## Seam
`JsonBone` (a `RawBone`) stores arbitrary structures as a JSON string and
unpacks them to dict/list on read. Pass `schema=` (a JSON Schema) to constrain
what is accepted; the schema itself is validated at construction time via
`jsonschema.validators.validator_for(False).check_schema`.

## Rules
- `multiple`, `languages` and `indexed` are all asserted to be false. The value
  is one opaque blob - if you need to query inside it, model it with real bones.
- The schema is the only validation. Without it any parseable JSON is stored.
- The value must stay serializable by `utils.json.dumps` - a datastore entity
  limit applies to the resulting string.

## Traps
- Client input that is not valid JSON is retried with `ast.literal_eval`, so
  Python literals (`{'a': 1}`, `None`) are accepted too. The error reported on
  failure is the *JSON* error, not the Python one.
- `singleValueSerialize` ignores its `value` parameter and dumps
  `skel.accessedValues[name]` instead. Overriding `singleValueSerialize` in a
  subclass or serializing a value that is not in `accessedValues` breaks with
  a KeyError.
- The value is stored unindexed, so `unique=` on this bone cannot work.
- Nothing sanitizes the content: strings inside the structure reach templates
  and JSON responses as-is (it is a `RawBone`).

## See also
[raw](raw.md), [base](base.md)
