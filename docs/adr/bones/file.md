---
covers: [viur.core.bones.file.FileBone, viur.core.bones.file.ensureDerived]
status: accepted
---
## Seam
`FileBone` is a `TreeLeafBone` fixed to `kind = "file"`, with the file-specific
mirror set `DEFAULT_REFKEYS` and validation of the referenced file
(`validMimeTypes` with `image/*` wildcards, `maxFileSize`, `public`).

Derived files: `derive={"<name>": <params>}` maps a key of
`conf.file_derivations` to its parameters. `postSavedHandler` queues the
deferred `ensureDerived`, which calls the deriver, merges the result into
`skel["derived"]["files"]` and re-triggers `update_relations` for the mirrored
`derived` values.

Extend by adding your own deriver to `conf.file_derivations` - not by
overriding `ensureDerived`.

## Rules
- `refKeys` must contain `dlkey` and `name` (ValueError otherwise). If you
  narrow `refKeys`, keep `mimetype`, `size` and `public` too - `isInvalid`
  reads them and raises KeyError when they are missing.
- `public` on the bone must match the referenced file's `public` flag; a
  public file cannot be selected by a private bone and vice versa.
- A deriver must return a list of `(filename, size, mimetype, custom_data)`
  tuples; anything else fails the assert in `ensureDerived`.
- Derive parameters must be JSON-serializable - they travel through a deferred
  task and are hashed into `deriveStatus` to decide whether a rebuild is due.

## Traps
- `ensureDerived` is re-queued by `update_relations`, which is why
  `postSavedHandler` bails out when the current request is a deferred
  `update_relations` for the `derived` bone, and why the follow-up
  `update_relations` runs with `_countdown=30`. Removing either guard produces
  an endless derive loop.
- The deprecated-kwarg shim at the top of `ensureDerived` assigns to
  `locals()`, which has no effect - passing `srcKey`/`deriveMap`/`refreshKey`
  warns and then silently loses the value.
- `refresh` has a side effect: for public images without a `serving_url` it
  patches the *referenced file entry*, not just the mirrored copy.
- `isInvalid` reads `value["dest"]["mimetype"]` without a None check, so a
  file entry without mimetype raises AttributeError during validation.
- `_atomic_dump` injects a freshly signed `downloadUrl` into the dumped value
  on every render, using `conf.render_json_download_url_expiration`. The dumped
  dict is therefore not stable and must not be cached.
- The bone stores a copy of `derived`, so a rebuilt derive is only visible in
  referencing entities after `update_relations` has run.

## See also
[relational](relational.md), [tree](tree.md), [image](image.md),
[../modules/file](../modules/file.md), [../tasks](../tasks.md)
