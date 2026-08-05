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
  them.

## Traps
- `getReferencedBlobs` is what keeps embedded files alive. If you override it
  without collecting blob keys, the blob GC deletes files that are still
  referenced from the HTML.
- With `srcSet` set, `getReferencedBlobs` also *queues derives* as a side
  effect - a read path writes.
- `getUniquePropertyIndexValues` raises NotImplementedError for multi-language
  bones.
- `CollectBlobKeys` looks only at the `src` attribute, also for `<a>` tags -
  a file linked via `href` is not collected and can be garbage-collected away.
- The sanitizer drops tags without content (`tagCache`), so empty markup
  silently disappears; `cleanup()` carries a `FIXME: vertauschte tags` for
  interleaved tags.
- An invalid tag is replaced by a single space, which changes text content.

## Why not
`HtmlSerializer` is also used outside the bone: `EmailTransportSmtp` and
`EmailTransportAppengine` call `HtmlSerializer().sanitize(body)` without a
configuration to produce the plain-text alternative. With `validHtml=None`
every tag is stripped - that is the intended "to text" path, not a bug.

## See also
[raw](raw.md), [string](string.md), [file](file.md), [../email](../email.md),
[../config](../config.md)
