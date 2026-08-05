---
covers: [viur.core.decorators.exposed, viur.core.decorators.internal_exposed, viur.core.decorators.access, viur.core.decorators.skey, viur.core.decorators.force_ssl, viur.core.decorators.force_post, viur.core.decorators.cors]
status: accepted
---
## Seam
This is the trust boundary. Everything reachable from outside passes through a
`Method` object configured by these decorators:

- `@exposed` - routable; with a dict argument it also registers SEO aliases.
- `@internal_exposed` - `exposed = False`, callable only for
  `internalRequest` (templates), NotFound from outside.
- `@force_ssl`, `@force_post` - protocol constraints checked in `_route`.
- `@skey` - CSRF guard, `@access` - authentication plus authorization guard.
- `@cors(allow_headers=...)` - per-method CORS headers.

Own guards are appended to `Method.guards`. Every guard is called with the
keyword arguments `args`, `kwargs`, `varargs`, `varkwargs` - `@access` just
absorbs them via `*args, **kwargs`, `@skey` names them.

## Rules
- Every state-changing exposed method needs `@skey`. `@force_post` alone is
  not CSRF protection.
- `@access()` without any right still enforces authentication: no user means
  Unauthorized, or a Redirect when `offer_login` is set. `"root"` always
  passes before any other check.
- `allow_empty=True` is only defensible for methods that render a form when
  called without data - that is why `add`/`edit`/`clone` use it and `delete`
  does not.
- Decorator order does not change the flags (they all mutate the same `Method`
  object), but it changes guard order: guards run in reverse order of
  application, so the decorator closest to `def` runs last.
- A custom guard must raise, not return - the return value is discarded.

## Traps
- `@skey` validates at most once per request
  (`current.request.get().skey_checked`). An exposed method calling another
  `@skey`-protected method internally passes the second check for free.
- `@skey` pops its parameter out of `kwargs`; the method never sees it unless
  `forward_payload` names a target key.
- With `allow_empty` as a list/tuple, a request carrying *only* the listed keys
  needs no key; with `allow_empty=True` the presence of varargs/varkwargs
  decides - so adding `**kwargs` to a signature can weaken the guard.
- `@access(callable)` grants on a truthy return; a falsy return only continues
  with the next entry and never denies on its own.
- `force_ssl` has no effect on the development server and for internal
  requests.
- `Method.ensure` mutates an existing `Method`, so decorating a method
  inherited from a base class changes it for the base class too.

## Why not
`@access` evaluates `user["access"]` only. `Module.roles` is configuration for
the user module and admin tooling; no role resolution happens in the guard, so
a role alone never grants access at runtime.

## See also
[module](module.md), [prototypes](prototypes.md), [errors](errors.md),
[securityheaders](securityheaders.md)
