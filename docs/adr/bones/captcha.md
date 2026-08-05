---
covers: [viur.core.bones.captcha.CaptchaBone]
status: accepted
---
## Seam
`CaptchaBone` verifies a Google reCAPTCHA (v2 and v3) token server-side. It is
not a storage bone: `serialize` always returns False, `unserialize` puts the
**public** key into the value so the frontend can render the widget, and
`fromClient` is overridden completely to do the verification.

Credentials come from `publicKey`/`privateKey` per bone or from
`conf.security.captcha_default_credentials` (`sitekey`, `secret`).
`score_threshold` applies to v3 only.

## Rules
- `privateKey` must be resolvable at class-definition time, otherwise the
  constructor raises ValueError - a missing secret breaks the import, not the
  request.
- The bone forces `required = True`; there is no optional captcha.
- Verification is skipped on the development server and for `root` users
  unless `conf.security.captcha_enforce_always` is set. Never test the captcha
  path as root.
- The token may arrive under the bone name or as `g-recaptcha-response`.

## Traps
- `fromClient` does a synchronous outbound `requests.post` with a 10 s timeout
  inside the request. A slow reCAPTCHA API slows down every form submission,
  and a non-OK response raises ValueError - a 500, not a validation error.
- Because verification lives in `fromClient` and not in `isInvalid`, a
  `vfunc` on this bone is never called.
- `skel["captcha"]` returns the public sitekey. It is meant to be shipped to
  the client - do not "fix" it by hiding the value, the widget needs it.
- The skipped paths return `None` (= valid) without touching the value, so a
  skeleton validated on the dev server carries no evidence that a captcha was
  ever solved.
- v2 responses have no `score`, so `score_threshold` is silently unused there.

## See also
[base](base.md), [spam](spam.md), [../config](../config.md)
