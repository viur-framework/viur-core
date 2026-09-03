---
covers: [viur.core.modules.file.File, viur.core.modules.file.FileLeafSkel,
         viur.core.modules.file.FileNodeSkel, viur.core.modules.file.DownloadUrlBone,
         viur.core.modules.file.thumbnailer, viur.core.modules.file.cloudfunction_thumbnailer,
         viur.core.modules.file.doCheckForUnreferencedBlobs,
         viur.core.modules.file.doCleanupDeletedFiles,
         viur.core.modules.file.start_delete_pending_files]
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
  `session["pendingFileUploadKeys"]` (last 50 entries) - but only as a
  fallback after `canAdd` failed, and the marker is consumed on use.
- `download` without `sig` is meant to be a root / `file-view` path, but it is
  unreachable: the blobKey is base64-decoded and split before the branch, so a
  raw storage path fails with BadRequest, and a signed payload without `sig`
  looks up the base64 string as the blob name and ends in Gone.
- `create_download_url(expires=<int>)` means *minutes*, and the expiry has
  minute granularity. `expires=None` yields a permanently valid, publicly
  cacheable url - `render_*_download_url_expiration` in conf is what usually
  keeps it short.
- Renaming a leaf copies and deletes the blob inside `onEdit`. A missing source
  blob raises `Gone` after the skeleton has already been read for the edit,
  and the copy uses `if_generation_match=0`, so an existing blob at the target
  name fails the request from the storage side.
- `serving_url` is injected on `write()` and `refresh()`, only for public image
  files, never on the development server (the API raises there) - and every
  other failure is swallowed with a log line, so a missing `serving_url` is a
  silent state.
- `FileLeafSkel.preProcessBlobLocks` locks its own `dlkey` unless the file is
  `weak` - that is what keeps an uploaded file alive without a FileBone.
- `File.deleteRecursive` no longer exists; `Tree.deleteRecursive` is inherited
  as-is and the File-specific blob marking hangs in `onDeleteRecursive`.

## Why not
Image width/height are not written during the request: `onAdded` defers
`set_image_meta`, and files above `IMAGE_META_MAX_SIZE` (10 MiB) are skipped
entirely. Code must tolerate a FileSkel without dimensions.

## See also
[prototypes](../prototypes.md), [tasks](../tasks.md),
[skeleton](../skeleton.md), [config](../config.md)
