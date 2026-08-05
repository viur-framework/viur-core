---
covers: [viur.core.bones.credential.CredentialBone]
status: accepted
---
## Seam
`CredentialBone` (a `StringBone`) stores a secret that can be written but
never read back: `unserialize` returns nothing, `serialize` writes only when a
new, non-empty value was set, and the property is always excluded from
indexes.

Use it for API keys and comparable secrets that the application itself needs
in plaintext. For user passwords use [password](password.md), which hashes.

## Rules
- The value is stored **in plaintext** in the datastore. It is hidden from
  clients, not encrypted. Do not treat this bone as password storage.
- `multiple` and `languages` are rejected in the constructor.
- `max_length` defaults to `None` (unlimited) here, unlike `StringBone`.
- An empty submitted value keeps the stored one. A secret can be replaced, but
  never cleared through the bone.

## Traps
- `skel["secret"]` is always `None` after a read, so read-modify-write cycles
  silently drop the value unless the client sends it again. `skel.patch()` on
  another bone is safe (nothing is written), but a manual
  `skel["secret"] = skel["secret"]` erases nothing and writes nothing.
- Because the bone is never indexed, you cannot query by it - not even
  `unique=` works reliably.
- `unserialize` returns `{}` instead of a bool, which does not match the
  `BaseBone` contract; the effective result is that `accessedValues` is never
  filled.

## See also
[string](string.md), [password](password.md), [base](base.md)
