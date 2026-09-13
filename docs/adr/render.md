---
covers: [viur.core.render.abstract.AbstractRenderer, viur.core.render.json.default.DefaultRender,
         viur.core.render.html.default.Render, viur.core.render.html.utils,
         viur.core.render.vi.getStructure, viur.core.render.vi.canAccess]
status: accepted
---
## Seam
A renderer subclasses `AbstractRenderer`; `kind`, `list` and `view` are
abstract, `add` and `edit` are not - they return `None` unless implemented. A
renderer is attached per module by the renderer-named class flag (see
[module](module.md)). Whole renderer namespaces are discovered in
`__build_app`, which collects every name in a module of `viur.core.render`
that points at an `AbstractRenderer` subclass - the name `DefaultRender`
itself is skipped so the same class is not registered twice, and the entry
point of a namespace is the name `default`. A `_postProcessAppObj(obj)` in
that package injects extra routes (that is how `/json/skey` and the whole
`/vi/*` API get in).

Per-module template overrides on the html render: the class attributes
`listTemplate`, `viewTemplate`, `addTemplate`, ... are looked up on
`self.parent` first. Jinja extension points: a module method `jinjaEnv(env)`,
plus `render.html.utils.getGlobalFunctions/Filters/Tests/Extensions`.

## Rules
- Set `kind` - other code branches on it, e.g. the prototypes enable
  `allow_client_defined` only for `json*` renderers.
- Serialize values through `skel.dump()` / `bone.dump()`.
  `DefaultRender.renderSkelValues` and `renderBoneValue` are deprecated
  since 3.8 and only forward there.
- While `skel.renderPreparation` is set the skeleton must not be modified
  (asserts in `read`/`write`/`fromClient`). Use `without_render_preparation()`
  when template code needs the raw value.

## Traps
- `renderPreparation` is contagious: the html render assigns it to nested
  `dest`/`rel` skeletons of relational and record bones as well, and results
  are cached in `renderAccessedValues`. `remove_render_preparation_deep()`
  exists precisely because clearing it on the outer skeleton is not enough.
- `render_action_template` adds a `skey` bone and a fresh security key to the
  skeleton - rendering a form mutates the skeleton you passed in. A request
  parameter `nomissing=1` additionally clears the skeleton's error list before
  the template sees it.
- The Jinja environment is built once per renderer instance and cached in
  `self.env`; a module's `jinjaEnv` runs only during that first build.
- `getTemplateFileName` tries language subdir, `?style=` postfix and the
  `<prefix>_<rest>.html` directory split, and falls back to the core template
  directory - a missing project template is silently served from the core.
- html `render()` raises `errors.Redirect` when `next_url` is given, while the
  json render returns it as a field. The same module code behaves differently
  per renderer.
- `renderBoneValue` returns `""` for password bones and `LanguageWrapper` for
  multi-language bones - a template never sees the plain dict.

## Why not
`vi` is the json renderer with `kind = "json.vi"` plus its own
`_postProcessAppObj`; `admin` is only an alias for `vi` (VIUR3 deprecation).
There is no separate admin renderer to hook into - extend `vi`.

Access control for the whole vi namespace is `render.vi.canAccess`, evaluated
by the router as a `canAccess` entry in the resolver dict, not by a decorator.
The router's own TODO calls this out as temporary.

## See also
[module](module.md), [skeleton](skeleton.md), [i18n](i18n.md),
[decorators](decorators.md)
