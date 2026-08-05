---
covers: [viur.core.modules.file.File, viur.core.modules.file.FileLeafSkel, viur.core.modules.file.thumbnailer, viur.core.modules.file.cloudfunction_thumbnailer]
status: accepted
---
## Seam
`File` is a `Tree` over `FileLeafSkel` / `FileNodeSkel`. Extension points:

- Derived files: `conf.file_derivations` maps a name to a callable
  (`thumbnailer` for in-process PIL, `cloudfunction_thumbnailer` for the
  external service plus `conf.file_thumbnailer_url`), selected per `FileBone`
  via `derive=`.
- Public files: a `dlkey` ending in `_pub` (`PUBLIC_DLKEY_SUFFIX`) routes
  `get_bucket` to the public bucket. Nothing else distinguishes them.
- Access to bytes from code: `File.write()` / `File.read()`.
- Urls: `create_download_url` / `parse_download_url` (`/file/download`,
  hmac-signed) and `create_internal_serving_url` (`/file/serve`, proxying
  googleusercontent).

## Rules
- Filenames must pass `File.is_valid_filename` (no Windows-reserved names, no
  control characters, `MAX_FILENAME_LEN`) - for uploads and for
  `download_filename`.
- Never assemble a download url by hand. `conf.file_hmac_key` signs
  `path\0expiry\0download_filename`; only `hmac_verify` decides access for
  unauthenticated requests.
- Do not mix public and private repositories: `getUploadURL` refuses when
  `public` does not match the root node's `public` flag.
- Never delete a blob directly. Use `mark_for_deletion` and let the periodic
  garbage collection decide - a blob still listed in any `viur-blob-locks`
  entry must survive.
- `/file/serve` parameters are restricted to `SERVE_VALID_OPTIONS` and
  `SERVE_VALID_FORMATS` because they are forwarded to Google verbatim. Keep
  new parameters allow-listed the same way.

## Traps
- Uploads are two-phase: `getUploadURL` creates a *pending*, weak FileSkel
  (name suffixed `PENDING_POSTFIX`) and immediately marks the dlkey for
  deletion. Only `file/add` with `skelType="leaf"` clears `pending`. Pending
  skeletons older than 7 days are deleted by `start_delete_pending_files`.
- A signed upload url authorizes the later `add()` through
  `session["pendingFileUploadKeys"]` (last 50 entries), not through module
  permissions.
- `download` without `sig` is a root / `file-view` path only, and is
  deliberately excluded from caching (`validUntil = "-1"`).
- `create_download_url(expires=None)` yields a permanently valid, publicly
  cacheable url - `render_*_download_url_expiration` in conf is what usually
  keeps it short.
- Renaming a leaf copies and deletes the blob inside `onEdit`. A missing source
  blob raises `Gone` after the skeleton has already been read for the edit.
- `serving_url` is injected only for public image files, and never on the
  development server (the API raises there).
- `FileLeafSkel.preProcessBlobLocks` locks its own `dlkey` unless the file is
  `weak` - that is what keeps an uploaded file alive without a FileBone.
- `File.deleteRecursive` still filters on the legacy `parentdir` property,
  while `Tree.deleteRecursive` uses `parententry`. Do not copy it as a
  template.

## Why not
Image width/height are not written during the request: `onAdded` defers
`set_image_meta`, and files above `IMAGE_META_MAX_SIZE` (10 MiB) are skipped
entirely. Code must tolerate a FileSkel without dimensions.

## See also
[prototypes](../prototypes.md), [tasks](../tasks.md),
[skeleton](../skeleton.md), [config](../config.md)
