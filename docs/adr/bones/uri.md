---
covers: [viur.core.bones.uri.UriBone]
status: accepted
---
## Seam
`UriBone` validates URIs with `urllib.parse.urlparse` and a set of policy
options: `accepted_protocols`, `accepted_ports` (int, `"2"`, `"1-4"`,
`"1,5-7"`, `"*"`, or an iterable thereof - normalized into a list of `range`),
`domain_allowed_list` xor `domain_disallowed_list`, `clean_get_params` (drop
the query string) and `local_path_allowed` (accept scheme-less paths and
prefix them with `/`).

## Rules
- `accepted_protocols` entries are fnmatch patterns: `["http*"]` allows `http`
  and `https`.
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
  `s`. And because `"*" in accepted_protocols` is a substring test on a
  string, `UriBone(accepted_protocols="http*")` disables the protocol check
  entirely - `file://` passes. Pass a list/tuple/set.
- A domain list cannot be combined with `local_path_allowed=True`: every
  scheme-less value is rejected with "Provided URL has no hostname specified".
- An empty list is not "no restriction". `domain_allowed_list=[]` rejects
  every URL, and the mutual-exclusion check tests truthiness, so an empty list
  next to a filled one passes the constructor. Same for `accepted_ports=0`,
  which disables the port check instead of raising.
- `accepted_ports` is compared against `parsed_url.port`, which is `None` when
  the URL uses the scheme default. With `accepted_ports=(443,)` the perfectly
  valid `https://example.com` is rejected because `None` is not in the range.
- `parsed_url.port` raises ValueError for a malformed port and `isInvalid`
  only wraps the `urlparse` call, so `http://host:abc` escapes as a 500
  instead of a validation error - but only when `accepted_ports` is set.
- `clean_get_params` rebuilds the URL through a hand-rolled namedtuple whose
  field order feeds `urlunparse` positionally - the fragment survives, the
  query is dropped, and the path parameters (`/a;jsessionid=42`) are dropped
  along with it.
- Nothing type-checks the value: a non-string raises AttributeError, and `""`
  with `local_path_allowed=True` raises IndexError on `value[0]`. Both are
  reachable through `setBoneValue`, which skips `isEmpty`.
- `structure()` exports the port ranges as `(start, stop)` pairs, i.e. the
  exclusive `range.stop` - the frontend sees one more than the highest allowed
  port.

## See also
[base](base.md), [string](string.md)
