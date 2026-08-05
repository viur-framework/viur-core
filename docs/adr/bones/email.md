---
covers: [viur.core.bones.email.EmailBone]
status: accepted
---
## Seam
`EmailBone` is a `StringBone` whose only addition is `isInvalid`: a syntactic
check of the address (length limits, one `@`, allowed local-part characters
including Unicode, and per-label DNS validation of the IDNA-encoded domain).

Override `isInvalid` (or pass `vfunc`) for extra policy - deliverability,
blocked domains, MX checks. None of that happens here.

## Rules
- The check is syntax only. A syntactically valid address is not a reachable
  one; do not use this bone as proof of ownership.
- Domain labels are validated with `_DNS_LABEL_RE` on the IDNA form because
  `idna.ToASCII` accepts leading/trailing hyphens and over-long labels - keep
  that check if you override the validation, otherwise `foo@-online.de`
  passes.
- A domain needs at least two labels and the TLD must not be all digits, so
  `user@localhost` and IP-literal domains are rejected by design.

## Traps
- An empty value is reported as invalid ("No value entered") rather than
  empty, so an optional EmailBone still needs `isEmpty` to filter first - which
  `BaseBone.fromClient` does before calling into the bone.
- `max_length` is inherited from `StringBone` (254) and the local part is
  limited to 64; both are enforced in addition to the regex.
- The bone escapes HTML like every `StringBone`, so an address containing
  `&` is stored escaped.

## See also
[string](string.md), [phone](phone.md), [../email](../email.md)
