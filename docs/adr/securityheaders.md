---
covers: [viur.core.securityheaders.addCspRule, viur.core.securityheaders.extendCsp, viur.core.securityheaders.setPermissionPolicyDirective]
status: accepted
---
## Seam
Project-wide, **before** `setup()`: `addCspRule`,
`enableStrictTransportSecurity`, `setXFrameOptions`, `setXXssProtection`,
`setXContentTypeNoSniff`, `setXPermittedCrossDomainPolicies`,
`setReferrerPolicy`, `setPermissionPolicyDirective`, `setCrossOriginIsolation`
- or the corresponding `conf.security.*` attributes directly.

Per request: `extendCsp(additionalRules, overrideRules)`.

Headers not covered by this module have to be set in a request preprocessor
(`conf.request_preprocessor`) - the module docstring says so explicitly.

## Rules
- `addCspRule` only works before `buildApp` (assert `conf.main_app is None`),
  because `setup()` builds the header cache once afterwards.
- Never put a nonce into the project-wide config; it would be reused across
  requests. `addCspRule` deliberately refuses to quote `nonce-` values, while
  `extendCsp` does quote them - the per-request path is the only correct one.
- `srcOrDirective` must not contain `;`, quotes, `,` or newlines (assert): no
  header injection through configuration.
- `extendCsp` affects only the `enforce` set, not `monitor`.
- Review the defaults per project. They already allow
  `storage.googleapis.com` images and Google sign-in sources - this is not a
  minimal policy.

## Traps
- `extendCsp` rebuilds and *replaces* the whole `Content-Security-Policy`
  response header from project config plus the given rules. A header set
  manually before that call is lost.
- `conf.security.content_security_policy` and `permissions_policy` keep their
  rendered header under the key `_headerCache` inside the same dict. Iterating
  them naively emits it as a directive; the `_rebuild*` functions filter it.
- `setup()` asserts that the CSP header cache contains only
  `Content-Security-Policy*` keys and that `strict_transport_security` starts
  with `max-age` - a hand-written value crashes startup instead of being
  ignored.
- Only the values `self`, `unsafe-inline`, `unsafe-eval`, `script`, `none` and
  hash/nonce prefixes get quoted; everything else is emitted verbatim, so a
  keyword this module does not know silently becomes a hostname.
- `extendCsp` requires at least one of its two arguments (assert).
- A `report-uri` is supported but of limited use in production - browser
  extensions flood it (note in `addCspRule`).

## Why not
The error page generates a per-request style nonce and calls `extendCsp` unless
`unsafe-inline` is already allowed for `style-src`. That is why error templates
may carry inline styles although the default policy forbids them - don't
"fix" the policy for that case.

## See also
[config](config.md), [decorators](decorators.md), [errors](errors.md),
[render](render.md)
