---
covers: [viur.core.bones.phone.PhoneBone]
status: accepted
---
## Seam
`PhoneBone` is a `StringBone` with a configurable regex (`test=`, default
`DEFAULT_REGEX`), a `max_length` of 15 (ITU-T E.164, counted on digits only)
and optional normalization through `default_country_code`.

Normalization order in `singleValueFromClient`: strip, `00` -> `+`, then
prefix `default_country_code` and drop a leading `0` of the local part.

## Rules
- `default_country_code` must match `^\+\d{1,3}$` (ValueError otherwise).
- The regex is the whole validation. Replacing `test=` replaces the format
  policy - the length check on extracted digits still runs on top.
- Set `test=None` only if something else validates; the bone then accepts any
  string within the length limit.

## Traps
- `max_length` is checked against `_extract_digits(value)`, which keeps `+`
  as well - so the effective limit is 15 characters including the plus, not 15
  digits.
- `self.test` is assigned *before* `super().__init__()`. That works only
  because the attribute guard in `BaseBone.__setattr__` is inactive during
  construction; do not copy the order into code that runs later.
- Normalization happens before validation, so what is stored is not what the
  client sent - a project reading the raw request value and the bone value
  gets two different strings.
- `structure()` exposes the regex pattern to the frontend, which is expected
  to re-implement it. A pattern using Python-only regex features cannot be
  evaluated there.

## See also
[string](string.md), [email](email.md)
