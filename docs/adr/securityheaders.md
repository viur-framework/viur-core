---
covers: [viur.core.config.Security.add_csp_rule, viur.core.config.Security.extend_csp,
         viur.core.config.Security.set_reporting_endpoint,
         viur.core.config.Security.set_permission_policy_directive,
         viur.core.config.Security.enable_strict_transport_security,
         viur.core.config.Security.set_x_frame_options, viur.core.config.Security.set_x_xss_protection,
         viur.core.config.Security.set_x_content_type_no_sniff,
         viur.core.config.Security.set_x_permitted_cross_domain_policies,
         viur.core.config.Security.set_referrer_policy,
         viur.core.config.Security.set_cross_origin_isolation,
         viur.core.config.Security.finalize, viur.core.config.Security.update_response_headers,
         viur.core.securityheaders]
status: accepted
---
## Seam
Everything lives on `conf.security` (`viur.core.config.Security`). Project-wide,
**before** `setup()`: `add_csp_rule`, `set_reporting_endpoint`,
`enable_strict_transport_security`, `set_x_frame_options`,
`set_x_xss_protection`, `set_x_content_type_no_sniff`,
`set_x_permitted_cross_domain_policies`, `set_referrer_policy`,
`set_permission_policy_directive`, `set_cross_origin_isolation` - or the
corresponding attributes directly.

Per request: `conf.security.extend_csp(additional_rules, override_rules)`.

`setup()` calls `conf.security.finalize()` once (builds the derived header
strings, validates); `Router` calls `conf.security.update_response_headers()`
per request. The module `viur.core.securityheaders` only keeps the old
camelCase functions as deprecating delegators (#1013).

Headers not covered here have to be set in a request preprocessor
(`conf.request_preprocessor`).

## Rules
- `add_csp_rule` only works before `buildApp` (assert `conf.main_app is None`),
  because `finalize()` builds the header cache once afterwards.
- Never put a nonce into the project-wide config; it would be reused across
  requests. `add_csp_rule` deliberately refuses to quote `nonce-` values, while
  `extend_csp` does quote them - the per-request path is the only correct one.
- `src_or_directive` must not contain `;`, quotes, `,` or newlines (assert): no
  header injection through configuration.
- `object_type` is checked against a fixed list of known CSP directives
  (assert), so a directive not in the list cannot be configured at all - it
  aborts startup instead.
- `extend_csp` affects only the `enforce` set, not `monitor`. An entry in
  `override_rules` whose value is `None` removes that directive for this
  request - the only way to drop a project-wide directive.
- Reporting endpoints (`set_reporting_endpoint`) are validated on set *and*
  again in `finalize()`; a `report-to` directive naming an unknown endpoint
  only logs a warning, the browser drops those reports silently.
- Review the defaults per project. They already allow
  `storage.googleapis.com` images and Google sign-in sources - this is not a
  minimal policy.

## Traps
- `extend_csp` rebuilds and *replaces* the whole `Content-Security-Policy`
  response header from project config plus the given rules. A header set
  manually before that call is lost.
- The rendered header strings live in private `Security` attributes
  (`_csp_header_cache`, `_permissions_policy_header`), not inside the config
  dicts any more - the former magic `_headerCache` key is gone. Mutating
  `content_security_policy` after `finalize()` has no effect on the emitted
  header until `_build_csp_header_cache()` runs again.
- `report-uri` and `report-to` get replaced instead of extended - every other
  directive accumulates its values.
- `finalize()` *raises* `AssertionError` (not a bare `assert`, so `python -O`
  does not remove it) when the CSP header cache holds anything but
  `Content-Security-Policy*` keys, or when `strict_transport_security` does
  not start with `max-age` - a hand-written value crashes startup instead of
  being ignored.
- Only the values `self`, `unsafe-inline`, `unsafe-eval`, `script`, `none` and
  hash/nonce prefixes get quoted; everything else is emitted verbatim, so a
  keyword this module does not know silently becomes a hostname.
- `extend_csp` requires at least one of its two arguments (assert).
- Reporting (`report-uri` / `report-to`) is of limited use in production -
  browser extensions flood the endpoint (note in `set_reporting_endpoint`).

## Why not
The error page generates a per-request style nonce and calls `extend_csp` unless
`unsafe-inline` is already allowed for `style-src`. That is why error templates
may carry inline styles although the default policy forbids them - don't
"fix" the policy for that case.

## See also
[config](config.md), [decorators](decorators.md), [errors](errors.md),
[render](render.md)
