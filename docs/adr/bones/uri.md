---
covers: [viur.core.bones.uri.UriBone]
status: accepted
---
## Seam
`UriBone` validates URIs with `urllib.parse.urlparse` and a set of policy
options: `accepted_protocols`, `accepted_ports` (int, `"1-4"`, `"*"`, or an
iterable thereof - normalized into a list of `range`), `domain_allowed_list`
xor `domain_disallowed_list`, `clean_get_params` (drop the query string) and
`local_path_allowed` (accept scheme-less paths and prefix them with `/`).

## Rules
- `domain_allowed_list` and `domain_disallowed_list` are mutually exclusive
  (ValueError). Both are lists/tuples of fnmatch patterns.
- Domain matching is `fnmatch(hostname, pattern) or pattern in hostname` - the
  substring fallback makes a pattern like `"example.com"` match
  `evil-example.com.attacker.net`. Anchor your patterns.
- `local_path_allowed=True` accepts input without a scheme. Anything built
  from such a value must not be used as a redirect target without a separate
  allow-list check.
- Validation happens per value; nothing normalizes case or percent-encoding.

## Traps
- `accepted_protocols` given as a plain string is passed through
  `set(...)`, which splits it into **characters**:
  `UriBone(accepted_protocols="https")` allows the protocols `h`, `t`, `p`,
  `s`. Pass a list/tuple/set.
- `accepted_ports` is compared against `parsed_url.port`, which is `None` when
  the URL uses the scheme default. With `accepted_ports=(443,)` the perfectly
  valid `https://example.com` is rejected because `None` is not in the range.
- `parsed_url.port` raises ValueError for a malformed port; `isInvalid` does
  not catch it, so the error escapes as a 500 instead of a validation error.
- `clean_get_params` rebuilds the URL through a hand-rolled namedtuple whose
  field order feeds `urlunparse` positionally - the fragment survives, the
  query is dropped.
- `structure()` exports the port ranges as `(start, stop)` pairs, i.e. the
  exclusive `range.stop` - the frontend sees one more than the highest allowed
  port.

## See also
[base](base.md), [string](string.md)
