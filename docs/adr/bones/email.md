---
covers: [viur.core.bones.email.EmailBone]
status: accepted
---
## Seam
`EmailBone` is a `StringBone` whose only addition is `isInvalid`: a syntactic
check of the address (length limits, one `@`, allowed local-part characters
including Unicode, the RFC 5321 dot rules for the local part - no leading or
trailing dot, no `..` - and per-label DNS validation of the IDNA-encoded
domain).

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
- `isInvalid` does not call `super().isInvalid()`, so neither `max_length` nor
  `min_length` of the `StringBone` is validated. The only length checks are the
  local `len(value) < 256` and the 64 characters of the local part.
  `StringBone.singleValueFromClient` afterwards truncates the value to
  `max_length` (254) inside `utils.string.escape(value, self.max_length)`, so a
  255 character address passes validation and is stored cut off.
- The bone escapes like every `StringBone`, but `&` is not part of the escape
  table - the characters that hit a valid address are `'` (`&#39;`) and `=`
  (`&#61;`). The escaped form contains a `;`, which is *not* in the allowed
  local-part characters: sending the stored address back unchanged (load and
  save in the admin) fails validation with "Invalid email entered".

## See also
[string](string.md), [phone](phone.md), [../email](../email.md)
