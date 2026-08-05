---
covers: [viur.core.module.Module, viur.core.module.Method]
status: accepted
---
## Seam
`Module` is the bare module prototype - no data model, no skeleton. Mark
callable methods with `@exposed`; every decorator turns the function into a
`Method` object which carries the routing flags. Overridable: `describe()`
(what admin tools see), `register()` (how methods land in the resolver),
`adminInfo` (dict or callable), `handler`, `roles`, `accessRights`,
`seo_language_map`.

Sub-modules are plain `Module` attributes and are registered recursively.
When methods or sub-modules are created at runtime, call `_update_methods()`.

## Rules
- A module without `handler` returns `None` from `describe()` and is invisible
  to admin tools. Set it (or a `@property`) when the module should be managed.
- Whether a module is built for a renderer is decided by a *class attribute
  named like the renderer* (`html`, `json`, `vi`, `admin`) being truthy - see
  `List.admin = True` / `List.vi = True`. No flag, no route in that namespace.
- A module must not be named like a renderer; startup raises NameError.
- `accessRights` entries are registered as `<moduleName>-<right>` into
  `conf.user.access_rights`, but only when `handler` is set as well.
- `self` and `return` are rejected as request parameters (BadRequest).

## Traps
- `describe()` caches into `self._cached_description`. Assign
  `self._cached_description = False` to keep a per-user description dynamic.
- `Method.__get__` returns a *copy* bound to the instance, so
  `module.method is module.method` is False. Do not use it as a dict key.
- `Method.__call__` parses arguments by annotation. Unannotated parameters
  arrive as raw `str` from the client; an annotation the parser does not know
  raises NotAcceptable at request time, not at startup.
- Parameters not in the signature are dropped silently unless the method
  accepts `**kwargs`.
- Guards from `@access`/`@skey` run in reverse order of application, i.e. the
  decorator written closest to `def` runs last - and always *after* the
  argument parsing.
- `Method.ensure` returns the same object when it is already a `Method`.
  Decorating an inherited method (`foo = access("x")(Parent.foo)`) therefore
  mutates the parent's Method for everybody.
- A module named `index` is mapped to the root: its methods land at the top
  level of the resolver.

## Why not
Routing walks the nested dicts in `conf.main_resolver`, not the module tree.
`conf.main_app.<module>` may hold the instance of the *last* built renderer
(explicitly called an "ugly solution" in `__build_app`), so never derive URLs
or renderer identity from it.

## See also
[decorators](decorators.md), [prototypes](prototypes.md), [render](render.md),
[errors](errors.md)
