---
covers: [viur.core.errors.HTTPException, viur.core.errors.Redirect,
         viur.core.errors.Unauthorized, viur.core.errors.Forbidden,
         viur.core.errors.NotFound, viur.core.errors.RequestTimeout,
         viur.core.errors.Locked, viur.core.errors.NotImplemented]
status: accepted
---
## Seam
Raise `viur.core.errors.*` from anywhere; the request handler translates them
into the response. Own status codes: subclass `HTTPException(status, name,
descr)`. Project-wide error rendering: `conf.error_handler(exception)` returning
a body, otherwise the template `<status>.html` or `error.html` is used
(resolved through the html render), with `conf.error_logo` passed in.

## Rules
- `Redirect` is control flow, not a failure: it defaults to 303, only
  301/302/303/307/308 are accepted (ValueError otherwise), and it is handled
  in its own except branch - status and `Location` are set, nothing is
  rendered and `conf.error_handler` is not consulted.
- `conf.error_handler` must return a non-empty `str`. A falsy return is
  discarded and the default rendering runs; anything that is not a `str` fails
  in `.encode()`.
- `descr` is translated at construction time (with `AddMissing.NEVER`) and is
  emitted as the `x-viur-error` response header. Never put internal detail,
  keys or user data into it.
- Anything not deriving from `HTTPException` becomes a 500 with the body
  discarded and the exception logged. Convert expected failures explicitly.
- `conf.debug.trace_exceptions` disables all of this handling - development
  only.
- `RequestTimeout` (408) is a protocol signal towards Cloud Tasks: raising it
  means "retry this task".

## Traps
- The response body is reset (`self.response.body = b""`) before an error is
  rendered, so partially written output is lost. A `Redirect` does *not* reset
  it - already written output is still sent with the 303.
- A redirect URL is normalized as `quote(unquote(url))` with `?`, `=`, `&` and
  `/` in the safe set, so percent-encoding does not survive:
  `?next=%2Fa%3Fb%3D1` becomes `?next=/a?b=1`. Never build a redirect URL from
  data that has to stay encoded.
- On the development server `error_info` carries the full traceback into the
  JSON body and the error template.
- JSON or HTML is chosen by the first path segment (`vi`, `json`) or an already
  set `application/json` Content-Type - the same exception renders differently
  depending on the route.
- The prototypes raise `Unauthorized` (401) for failed `canEdit`/`canDelete`
  checks, so an authenticated user without rights sees a 401 where 403 would be
  expected. `Forbidden` is used in only a few places.
- `errors.NotImplemented` shadows the Python builtin inside that module.
- `HTTPException.process()` exists and does nothing (with a TODO asking why).
- `Locked` (423) is raised by `Skeleton.delete` when a `PreventDeletion`
  relation exists - catch it if a module offers a delete action.

## Why not
Exceptions carry no payload. Machine-readable information travels as the
`x-viur-error` header and, for json routes, the `error_info` dict - so adding
fields to an exception subclass does not reach the client.

## See also
[module](module.md), [decorators](decorators.md), [render](render.md),
[bones/relational](bones/relational.md)
