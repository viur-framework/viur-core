---
covers: [viur.core.bones.selectcountry.SelectCountryBone]
status: accepted
---
## Seam
`SelectCountryBone` is a `SelectBone` prefilled with ISO 3166-1 country lists.
`codes=SelectCountryBone.ISO2` (default) or `ISO3` selects the code length;
`values` may additionally be a subgroup name (`"dach"`, `"eu"` from
`subgroup_mappings`), a list of codes or a full dict.

`singleValueUnserialize` converts between alpha-2 and alpha-3 on read, so the
stored code length may differ from the configured one.

## Rules
- Extend `subgroup_mappings` (ISO2 codes) rather than passing hand-written
  lists around; the class converts them to ISO3 when needed.
- All codes are lowercase; pass and expect them that way.
- A `values` list must match the configured code length - the lookup into
  `ISO2CODES`/`ISO3CODES` raises `KeyError` for a mismatched code, as does an
  unknown subgroup name.
- Switching `codes` on an existing kind does not need a migration: existing
  values are converted on read. But queries still filter the *stored* code.

## Traps
- The lists are the ISO 3166-1 snapshot in this file (249 entries each) -
  country changes require editing the source, and `ISO2TOISO3` is derived from
  `ISO3TOISO2`, so a missing pair breaks both directions.
- The read-side conversion is silent: a bone switched from ISO3 to ISO2 hands
  out `"de"` while the datastore holds `"deu"`, so filtering by the value you
  just read finds nothing.
- Options are sorted by label, not by code - but only once in `__init__`, on
  the untranslated English names. The order in the frontend therefore stays
  English-alphabetical in every language.
- A `values` dict is passed through unchecked; only lists and subgroup names
  are validated against `codes`.
- The bone sets no `translation_key_prefix`, so the labels are translated under
  the bare code (`"de"`, `"deu"`) in the global translation namespace.
- Only lowercase codes are handled: `"DE"` is rejected as `Invalid`, and an
  uppercase code in the datastore is handed out without conversion.

## See also
[select](select.md), [../i18n](../i18n.md)
