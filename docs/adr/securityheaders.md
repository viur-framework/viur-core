---
covers: [viur.core.securityheaders.addCspRule, viur.core.securityheaders.extendCsp,
         viur.core.securityheaders.setPermissionPolicyDirective,
         viur.core.securityheaders.enableStrictTransportSecurity,
         viur.core.securityheaders.setXFrameOptions, viur.core.securityheaders.setXXssProtection,
         viur.core.securityheaders.setXContentTypeNoSniff,
         viur.core.securityheaders.setXPermittedCrossDomainPolicies,
         viur.core.securityheaders.setReferrerPolicy,
         viur.core.securityheaders.setCrossOriginIsolation]
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
- `objectType` is checked against a fixed list of known CSP directives
  (assert), so a directive the module does not list cannot be configured at
  all - it aborts startup instead.
- `extendCsp` affects only the `enforce` set, not `monitor`. An entry in
  `overrideRules` whose value is `None` removes that directive for this
  request - the only way to drop a project-wide directive.
- Review the defaults per project. They already allow
  `storage.googleapis.com` images and Google sign-in sources - this is not a
  minimal policy.

## Traps
- `extendCsp` rebuilds and *replaces* the whole `Content-Security-Policy`
  response header from project config plus the given rules. A header set
  manually before that call is lost.
- `conf.security.permissions_policy` keeps its rendered header under
  `_headerCache` *between* the real directives, which is why
  `_rebuildPermissionHeaderCache` filters that key out; iterating the dict
  naively emits it as a directive. In `content_security_policy` the key sits
  next to `monitor`/`enforce` instead, so the CSP rebuild never sees it.
- `report-uri` is the one directive that gets replaced instead of extended -
  every other one accumulates its values.
- `setup()` *raises* `AssertionError` (not a bare `assert`, so `python -O`
  does not remove it) when the CSP header cache holds anything but
  `Content-Security-Policy*` keys, or when `strict_transport_security` does
  not start with `max-age` - a hand-written value crashes startup instead of
  being ignored.
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
