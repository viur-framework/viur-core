---
covers: [viur.core.config.ConfigType, viur.core.config.Conf, viur.core.config.Security]
status: accepted
---
## Seam
`conf` is one `Conf` instance built at import time. Extend it by assigning
attributes, or add a whole section by subclassing `ConfigType` and
instantiating it with `parent=conf`. `_mapping` translates deprecated names to
current ones and emits a DeprecationWarning.

Project configuration belongs into the project's `main.py` before `setup()`.

## Rules
- Strict mode is the default: it is only off when
  `VIUR_CORE_CONFIG_STRICT_MODE` is literally `"false"`. In strict mode
  dict-style access, `.get()` and the alias mapping raise
  SyntaxError/AttributeError. Write new code against attributes only.
- Values that are consumed at class-definition time cannot be changed later:
  `conf.i18n.available_languages` is baked into `Skeleton.viurCurrentSeoKeys`
  and `FileLeafSkel.alt` when those classes are created. Set it before the
  skeletons are imported.
- CSP and permissions rules must be configured before `buildApp`
  (`addCspRule` asserts `conf.main_app is None`).
- `conf.security.closed_system_allowed_paths` is composed from
  `admin_allowed_paths` at class-definition time. Appending to
  `admin_allowed_paths` afterwards does not extend it.

## Traps
- `conf.instance.core_base_path` points into `site-packages`, not into the
  source tree (marked with a fixme). Don't use it to locate project files.
- `conf.instance.project_base_path` is `Path().absolute()` evaluated at import
  time, so it depends on the process working directory.
- `ConfigType.items()` evaluates `@property` members while iterating, and skips
  everything that already exists on `ConfigType` itself - the vi endpoints
  `config` and `settings` publish exactly what it yields.
- In non-strict mode `conf["a.b"] = x` creates the missing section on the fly
  with a warning, so a typo silently becomes a new config section.
- `conf.user.session_life_time` coerces non-timedelta values through a
  deprecated parse path.
- `conf.security.content_security_policy` and `permissions_policy` carry a
  `_headerCache` entry inside the same dict as the real directives.

## Why not
The dict interface and the mapping tables exist only to migrate ViUR 2/3
projects; strict mode is the default so that the old syntax fails loudly
instead of working by accident. Don't build new APIs on `conf[...]`.

`conf.compatibility` is a list of opt-in legacy behaviours (json structure
formats, `PeriodicTask` minutes, ...). Adding a flag changes wire formats -
treat it as a breaking change for clients, not as a setting.

## See also
[securityheaders](securityheaders.md), [render](render.md), [email](email.md),
[i18n](i18n.md), [tasks](tasks.md)
