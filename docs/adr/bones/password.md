---
covers: [viur.core.bones.password.PasswordBone, viur.core.bones.password.encode_password]
status: accepted
---
## Seam
`PasswordBone` hashes with PBKDF2-HMAC-SHA256 (`encode_password`,
`PBKDF2_DEFAULT_ITERATIONS = 600_000`) and stores a dict of `pwhash`, `salt`,
`iterations`, `dklen`. It can never be read back: `unserialize` always returns
False and `_atomic_dump` returns `""`.

Strength policy is the `tests` class attribute - tuples of
`(regex, hint, required)` - plus `test_threshold` (how many must pass,
default 4). Override `tests` for your own policy; `tests=()` is what actually
disables the suite.

## Rules
- The stored dict carries its own `iterations`/`dklen`, so old hashes stay
  verifiable when the defaults change. Never rewrite that structure by hand.
- Your regexes must behave identically in Python and JavaScript - the frontend
  re-runs them from `structure()`. That is documented on `tests` and it rules
  out lookbehind and named groups.
- `conf.user.max_password_length` truncates before hashing; it exists to bound
  PBKDF2 cost, not as a policy knob.
- `raw=True` only stops `fromClient` from hashing; it does not reach the
  datastore unhashed (see Traps). Only a value that is already a dict survives
  `serialize` untouched, which is the actual path for migrating pre-hashed
  data.

## Traps
- An empty submitted value is reported as `Empty` and the stored password is
  kept - deliberately, so a password can be changed but not deleted through
  the bone.
- `isInvalid` returns a **list** of hints, not a string, so
  `ReadFromClientError.errorMessage` is a list here. Anything formatting that
  message has to cope with both.
- `isInvalid` returns `False` for an empty value, i.e. "valid" - the emptiness
  is handled in `fromClient`, not by the validator.
- Assigning `skel["password"] = "secret"` works and is hashed in `serialize`,
  but skips the strength tests entirely.
- `serialize` distinguishes "already hashed" from "plaintext" purely by
  `isinstance(value, dict)`. That also defeats `raw=True`: `fromClient` puts
  the plain string into the skeleton, and `serialize` then hashes it because it
  is not a dict. The mode changes what `skel[name]` holds in memory, not what
  is written.
- `test_threshold=0` does not switch the suite off. The optional tests stop
  mattering, but a test marked `required` - the built-in 8 character minimum -
  still rejects the value. Meanwhile `structure()` reports an empty `tests`
  tuple for `test_threshold=0`, so the frontend validates nothing while the
  backend still refuses. Pass `tests=()` to really disable it.

## See also
[string](string.md), [credential](credential.md), [../config](../config.md)
