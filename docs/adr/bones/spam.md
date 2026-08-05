---
covers: [viur.core.bones.spam.SpamBone]
status: accepted
---
## Seam
`SpamBone` is a dependency-free alternative to [captcha](captcha.md): a
`NumericBone` that asks the user to add two numbers. The two operands are
rolled in the `descr` **property** and stored in the session
(`spambone.value.a` / `.b`); `isInvalid` compares the answer and consumes them.

Customize via `descr` (the question template, with `{{a}}`/`{{b}}`), `values`
(the words used for the digits) and `msg_invalid`.

## Rules
- `precision` cannot be passed (ValueError) - the answer is always an integer.
- At least two `values` are required.
- The question is generated when `descr` is read, i.e. when the form is
  rendered or the structure is requested. A client that never fetched the
  structure has no operands in its session.
- Each validation consumes the operands, so every attempt needs a freshly
  rendered question. This is the anti-replay property - do not cache it away.

## Traps
- The values live in the session, so the bone does not work for sessionless
  API clients, and it is per session, not per form: two forms rendered in
  parallel share (and overwrite) the same operands.
- `descr` returns `None` while the system is not initialized, which is why the
  property exists at all - `BaseBone.setSystemInitialized` would otherwise
  freeze a question into the bone.
- The `descr` setter is intentionally a no-op so that `BaseBone.__init__` can
  assign to it. Assigning `descr` later silently does nothing.
- If the operands are missing from the session, `a` and `b` are `0` and the
  answer is compared against `0` as an **int** while the client value stays a
  string - so validation always fails rather than always passing.
- `descr` and `values` are evaluated as default arguments at import time,
  which makes the translate objects module-level singletons.

## See also
[numeric](numeric.md), [captcha](captcha.md), [../i18n](../i18n.md)
