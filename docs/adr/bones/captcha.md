---
covers: [viur.core.bones.captcha.CaptchaBone]
status: accepted
---
## Seam
`CaptchaBone` verifies a **reCAPTCHA Enterprise** token server-side. It is not a
storage bone: `serialize` always returns False, `unserialize` puts the
**public** key into the value so the frontend can render the widget, and
`fromClient` is overridden completely to do the verification.

There is no shared secret. `fromClient` calls
`RecaptchaEnterpriseServiceClient.create_assessment()` against
`projects/{conf.instance.project_id}`, so the site key must live in the same
GCP project and the runtime credentials are what authenticates the call.

The site key comes from `public_key` per bone or from
`conf.security.captcha_default_public_key`. `render_challenge` only selects the
widget style (visible checkbox vs. invisible), and `recaptcha_action` is the
action name the client must have used.

## Rules
- `public_key` must be resolvable at class-definition time, otherwise the
  constructor raises ValueError - a missing site key breaks the import, not the
  request. `score_threshold` outside `(0, 1]` raises there too.
- `publicKey` still works as a constructor argument but emits a
  DeprecationWarning; new code uses `public_key`.
- The bone forces `required = True`; there is no optional captcha.
- Verification is skipped on the development server and for `root` users
  unless `conf.security.captcha_enforce_always` is set. Never test the captcha
  path as root.
- The token is read from `data[<bone name>]` only, and a missing token is a
  `NotSet` error.
- `structure()` exports `public_key`, `render_challenge` and `action` so the
  client can build the widget from the skeleton structure alone.

## Traps
- The `fromClient` docstring still claims `g-recaptcha-response` is accepted as
  an alternative field name. It is not - the code only looks up the bone name.
  A frontend posting the reCAPTCHA callback value verbatim fails with
  "Token not set".
- `create_assessment` is a synchronous outbound call inside the request, so
  every form submission waits for the reCAPTCHA Enterprise API.
- `render_challenge` does not disable scoring: the score is compared against
  `score_threshold` on every path, checkbox challenges included. Setting
  `render_challenge = True` and expecting a pure "did they click it" check is
  the classic misconfiguration.
- `recaptcha_action` defaults to `""` and is compared for exact equality with
  `response.token_properties.action`. Any client that sends an action while the
  bone was left at the default is rejected as "Invalid Action".
- The error messages carry the score and the expected action
  (`f"Invalid Captcha: {score}"`) and are handed to the client unmodified and
  untranslated.
- Because verification lives in `fromClient` and not in `isInvalid`, a
  `vfunc` on this bone is never called.
- `skel["captcha"]` returns the public site key. It is meant to be shipped to
  the client - do not "fix" it by hiding the value, the widget needs it.
- The skipped paths return `None` (= valid) without touching the value, so a
  skeleton validated on the dev server carries no evidence that a captcha was
  ever solved.

## See also
[base](base.md), [spam](spam.md), [../config](../config.md)
