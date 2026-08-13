---
covers: [viur.core.bones.image.ImageBone, viur.core.bones.image.ImageBoneRelSkel]
status: accepted
---
## Seam
`ImageBone` is a `FileBone` with three defaults changed: `public=True`,
`validMimeTypes=["image/*"]` and `using=ImageBoneRelSkel`, which adds a
multi-language `alt` bone to the *relation* (not to the file).

So the alternative text belongs to the usage of the image in this entry, not to
the file entity - two entries can describe the same image differently. The file
itself also carries an `alt` bone (`FileLeafSkel.alt`), but it is *not* part of
`FileBone.DEFAULT_REFKEYS`, so it never reaches `value["dest"]`. Using it as a
fallback requires adding `"alt"` to `refKeys` explicitly; nothing in the bone
falls back on its own.

Pass your own `using=` RelSkel (subclassing `ImageBoneRelSkel`) to carry extra
per-usage data such as a caption or a focus point.

## Rules
- `public=True` is the default here, so the referenced file must live in a
  public repository - `File.getUploadURL` refuses the mismatch. Pass
  `public=False` explicitly for private images.
- Because `using` is set, the client has to submit subfields
  (`<bone>.<index>.key`, `<bone>.<index>.alt.<lang>`); a plain key is not
  enough.
- `ImageBoneRelSkel.alt` uses `conf.i18n.available_languages` as evaluated at
  import time - configure the languages before the skeletons are imported.

## Traps
- Overriding `using` with a RelSkel that lacks `alt` silently drops the
  alternative text for that bone - nothing warns.
- `alt` is not `required`, so an image can always be saved without any
  alternative text. Enforce it in your own `using` skel if you need it.
- The `validMimeTypes` default is a mutable list literal in the signature
  (`= ["image/*"]`), shared by every `ImageBone` that does not pass its own.
  Mutating `bone.validMimeTypes` in place changes it for all of them.
- `public=True` means the served file is cacheable at the edge; a derived
  thumbnail of a private image is not automatically private just because the
  bone is.

## See also
[file](file.md), [relational](relational.md),
[../modules/file](../modules/file.md), [../config](../config.md)
