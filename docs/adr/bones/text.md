---
covers: [viur.core.bones.text.TextBone, viur.core.bones.text.HtmlSerializer, viur.core.bones.text.HtmlBoneConfiguration, viur.core.bones.text.CollectBlobKeys]
status: accepted
---
## Seam
`TextBone` stores sanitized HTML. The sanitizer is `HtmlSerializer`, driven by
a `HtmlBoneConfiguration` dict (`validTags`, `validAttrs`, `validStyles`,
`validClasses`, `singleTags`), defaulting to `conf.bone_html_default_allow`.

Extend the allow-list per bone via `validHtml=`, or project-wide by editing
`conf.bone_html_default_allow`. `validHtml=None` disables HTML completely
(everything becomes text). `srcSet=` makes the bone inject `srcSet` attributes
for embedded ViUR files and triggers the corresponding derives.

`CollectBlobKeys` is the counterpart used by `getReferencedBlobs` to keep
embedded files locked.

## Rules
- Sanitizing happens in `singleValueFromClient` only. A value assigned in code
  (`skel["text"] = "<script>"`) is stored as-is - `singleValueSerialize`
  passes it through unchanged.
- Extend `validAttrs` per tag; an attribute that is not listed for *that* tag
  is dropped even when it is valid elsewhere.
- Keep `indexed=False` (the default). With `indexed=True` you must lower
  `max_length` yourself - the datastore limit is not checked for you.
- Embedded `src` urls are rewritten to freshly signed, non-expiring download
  urls. Do not post-process them; `refresh` re-runs the sanitizer to rebuild
  them - but only when `srcSet` is set, otherwise `refresh` does nothing.
- `max_length` (default 200000) counts characters of the *unsanitized* input,
  not bytes and not what ends up stored.

## Traps
- `getReferencedBlobs` is what keeps embedded files alive. If you override it
  without collecting blob keys, the blob GC deletes files that are still
  referenced from the HTML.
- With `srcSet` set, `getReferencedBlobs` also *queues derives* as a side
  effect - a read path writes.
- `CollectBlobKeys` looks only at the `src` attribute, also for `<a>` tags -
  a file linked via `href` is not collected and can be garbage-collected away.
  The docstring of `getReferencedBlobs` claims otherwise.
- The `javascript:` guard compares `v.lower()[0:10]`; a tab inside the scheme
  (`java&#9;script:`) passes the sanitizer and is executed by the browser,
  which strips tabs from urls. `src` is unaffected, it is checked separately.
- The sanitizer drops tags without content (`tagCache`), so empty markup
  silently disappears; `cleanup()` carries a `FIXME: vertauschte tags` for
  interleaved tags.
- An invalid tag is replaced by a single space, which changes text content.
- Whitespace-only text nodes are dropped and `\n` is removed rather than
  replaced, so `<b>a</b> <b>b</b>` and `a\nb` lose their word boundary.
- `max_length` is checked before sanitizing. Escaping grows the value - a
  `"` becomes six characters - so the stored text can be a multiple of the
  limit and exceed what the datastore accepts.
- `isInvalid` calls `len(value)` after the `None` check only; a non-str from a
  JSON body raises TypeError instead of a validation error.
- `refresh` feeds the stored value back through `singleValueFromClient` and
  keeps only `[0]`. A value that fails validation - one grown past
  `max_length`, or a lowered limit - is replaced by the empty string, per
  language.
- `structure()` exports `valid_html` but not `max_length`, so the frontend
  cannot enforce the limit.
- `validHtml` defaults to the *shared* `conf.bone_html_default_allow` dict.
  Editing it in place through one bone changes it for every bone.

## Why not
`HtmlSerializer` is also used outside the bone: `EmailTransportSmtp` and
`EmailTransportAppengine` call `HtmlSerializer().sanitize(body)` without a
configuration to produce the plain-text alternative. With `validHtml=None`
every tag is stripped - that is the intended "to text" path, not a bug.

## See also
[raw](raw.md), [string](string.md), [file](file.md), [../email](../email.md),
[../config](../config.md)
