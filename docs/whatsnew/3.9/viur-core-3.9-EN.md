# What's new in viur-core 3.9?

This document describes the most significant changes with regard to viur-core 3.9.

## Database

### Memcache for the datastore

`db.get`, `db.put`, and `db.delete` now sit on top of a cache layer backed by Memcache. `db.get()` first tries to read the requested keys from the cache, and only the keys still missing are actually fetched from the datastore via `get_multi` and then written back into the cache. `db.put()` and `db.delete()` mirror every write accordingly into the cache.

Inside a running transaction the cache is bypassed entirely (neither read nor written), since a record that is currently being written within a transaction must not be cached.

The effect: repeated `db.get()` calls for the same keys within a request or process no longer trigger another datastore round trip.

To enable the memcache for ViUR, the following lines need to be added to `main.py`:

```py
from viur.core import conf
from google.appengine.api.memcache import Client as MemcacheClient

conf.db.memcache_client = MemcacheClient()
```

### Configurable database and namespaces

Google Cloud Datastore now supports multiple named databases per project as well as namespaces. This can now be configured via

- `conf.db.name` (or environment variable `VIUR_DB_NAME`)
- `conf.db.namespace` (or environment variable `VIUR_DB_NAMESPACE`)

> [!IMPORTANT]
> Since the datastore client is already built when `db.transport` is imported, the environment variables must be set before `viur.core` is imported. Setting `conf.db.name` at runtime afterwards no longer has any effect on the client that has already been created.

If nothing is configured, everything behaves as before (default database, no namespace) - the change is fully backward-compatible.

### Native datastore operators instead of client-side MultiQuery

Filters like `IN`, `!=`, and `NOT_IN` used to be split client-side into several sub-queries and then merged back together in code (`MultiQuery`). That cost unnecessarily many RPCs and caused `default_order` to no longer apply to such queries.

These filters are now passed directly to Cloud Datastore as native datastore operators - what used to be many partial requests becomes one.

In addition, there is now `Query.or_filter()` to natively express OR-combined condition groups:

```py
q = skel.all()
q.or_filter(("continent =", "Africa"), ("continent =", "Asia"))
q.or_filter(("sortindex >", 200), ("sortindex <", 50))  # ANDed with the group above
```

Multiple `or_filter()` calls are ANDed together, and with regular `filter()` calls as well.

### `keys_only` tooling for `Query`

When only the keys of a search result matter (e.g. for bulk deletions or plain existence checks), full entities no longer need to be loaded:

```py
keys = skel.all().filter("is_active =", False).keys_only()

# or via run()/iter():
keys = skel.all().run(keys_only=True)
```

This saves on read cost and data volume, but cannot be combined with full-text search.

### `QueryOrder`

Sort orders for a query can now be given in a typed form as `db.QueryOrder(name, order=SortOrder.Ascending)` or `db.QueryOrder(name, order=SortOrder.Descending)`, instead of as a loose tuple `(name, SortOrder)`. Existing calls using tuples keep working unchanged, since they are normalized internally.

### `Query.iter_skel()`

Analogous to `fetch()` being the streaming counterpart of `run()`, there is now `iter_skel()` as the counterpart to `iter()`: it streams large result sets via a cursor, but yields `SkeletonInstance` objects directly instead of raw `Entity` objects.

```py
for skel in someSkel.all().filter("is_active =", True).iter_skel():
    skel.patch({"touched": True})
```

`iter_skel()` only works on queries created via `skel.all()`, and not on multi-queries.

## Skeletons

### `preprocess` function for `Skeleton.patch()`

`Skeleton.patch()` now accepts an optional `preprocess` callable, which is executed within the same transaction immediately before `skel.write()` - i.e. after `values`, `create`, and `check` have already been applied, but before the record is persisted:

```py
def preprocess(skel):
    skel["touched"] = utils.utcNow()

skel.patch(values={"name": "New name"}, preprocess=preprocess)
```

This allows edit flows to be extended transaction-safely, without having to rebuild the whole patch/transaction logic yourself.

### Fix: compute bones during cascading deletion

When a skeleton is removed as part of a cascading deletion, compute bones (e.g. relational lookups) were still being evaluated - which could cause errors, because the referenced records were already in the process of vanishing. This is now prevented.

### Fix: `Skeleton.write()` must not resurrect removed bones

If a bone was removed from a skeleton at runtime (e.g. `skel.some_bone = None`, as happens with dynamically built SubSkels), `Skeleton.write()` used to write that bone's last known value back into the database anyway. Removed bones are now skipped entirely when writing; their referenced blobs are still correctly locked against the blob garbage collection, though.

## Bones

### `tags` feature for bones

Every bone can now be given a `tags` parameter to classify it in terms of content, e.g. for privacy, audit, or anonymization tooling:

```py
email = EmailBone(tags=("personal", "contact"))
```

Common values include `"personal"`, `"contact"`, `"identifier"`, `"location"`, `"financial"`, `"technical"`. The tags are also exposed via `bone.structure()`.

> [!IMPORTANT]
> `tags` is purely metadata classification and has no influence whatsoever on access rights.

Several bones within ViUR itself already come with tags preset, for example `KeyBone` with `tags="technical"` or `UserSkel.name` with `("personal", "identifier", "contact")`.

### New bones: `CodeBone`, `LogicsBone`, `JinjaBone`, and `PythonBone`

For code that is meant to be stored in the database and evaluated in the backend, there is now a dedicated bone family with syntax validation:

```py
class MySkel(Skeleton):
    formula = LogicsBone(descr="Formula")   # validated via the Logics expression language
    template = JinjaBone(descr="Template")  # validated via the Jinja2 parser
    script = PythonBone(descr="Script", validate=False)  # AST validation, disabled here
```

`CodeBone` itself is the generic base (no `multiple`, no `languages`) with the parameters `validate: bool = True` and `syntax: str | None` for frontend highlighting.

![LogicsBone, JinjaBone, PythonBone](codebones.png)

### `NumericBone` with decimal support

`NumericBone` can now compute internally with `decimal.Decimal` instead of float, via `decimal=True`:

```py
price = NumericBone(precision=2, decimal=True)
```

This stores values exactly, without rounding errors. Internally, the serialization form changes to `{"val": 19.99, "decimal": "19.99"}`: filtering and sorting continue to run against the (less precise, but indexable) float value in `val`, while the exact decimal number is preserved as a string in `decimal`. The JSON renderer supports the new format accordingly.

### `AddressBone`

A new, ready-made bone for addresses including automatic geocoding:

```py
address = AddressBone(descr="Address")
```

The underlying `AddressRelSkel` contains street, house number, address addition, ZIP code (validated against country-specific regex patterns), city, country, and coordinates. When saved, the entered address is automatically geocoded via Nominatim/OpenStreetMap; the resulting coordinates are cached in a dedicated datastore kind so that the (rate-limited) free API isn't queried more often than necessary.

![AddressBone](addressbone.png)

#### `after_from_client` hook

The geocoding in `AddressBone` is built on top of a new, generally usable hook: `after_from_client(skel, name, errors)` is called at the end of `fromClient()`, after the value has already been validated and written to the skeleton. Custom bones can use it to normalize the set value afterwards, or to add extra errors.

### `escape_html` for `TextBone`, and globally configurable

`TextBone` now has an `escape_html` parameter, analogous to `StringBone`:

```py
text = TextBone(escape_html=False)  # only allowed together with validHtml=None
```

> [!IMPORTANT]
> Setting `escape_html=False` removes XSS protection entirely, and files referenced within the text are no longer protected from deletion (`getReferencedBlobs()` then always returns an empty set).

For `StringBone`, the default can now also be controlled globally via `conf.bone_string_escape_html` (default: `True`), instead of having to repeat it on every single bone.

### `CaptchaBone`: migration to reCAPTCHA Enterprise

`CaptchaBone` now internally uses the reCAPTCHA Enterprise SDK instead of the old public REST endpoint. The parameters `publicKey`/`privateKey` are now called `public_key` (the old name still works, but raises a deprecation warning); `privateKey` is dropped entirely, since authentication now runs via the GCP service-account credentials. New additions are `render_challenge` (a visible checkbox instead of invisible v3-style scoring) and `recaptcha_action` for analytics/scoring. `conf.security.captcha_default_credentials` became `conf.security.captcha_default_public_key`.

### `RelationalBone`: performance and bugfixes

`RelationalBone.postSavedHandler` used to issue its own `db.put()` per relation and its own `db.delete()` per removed relation - on every save of a skeleton carrying relational bones. These writes are now collected and written in a single commit per save operation. Besides fewer round trips, this also brings real atomicity (previously part of the relations could be written while another part failed) and is gentler on the datastore's "one write per second per entity group" limit, since all `viur-relations` entries of a record share the same entity group.

Measured write duration for N entities, one `put()` per entity versus one batched `put()` (median of 3 measurements, real datastore):

| Entities | individually | batched | factor |
|---------:|-------------:|--------:|-------:|
| 1 | 79 ms | 72 ms | 1.1x |
| 10 | 525 ms | 86 ms | 6.1x |
| 100 | 5028 ms | 471 ms | 10.7x |
| 500 | 24933 ms | 2299 ms | 10.8x |

In addition, a `Lookup` in the datastore accepts at most 1,000 keys at once; `db.get()` now automatically splits larger requests into chunks and reassembles the result in the original order.

Also fixed: a bug in `RelationalBone.postDeletedHandler`. When deleting a record, its relation entries were queried with `query.run()`, which was implicitly capped at `conf.db.query_default_limit` (default: 30). Records with more than 30 relations in one bone therefore left orphaned entries behind in `viur-relations` upon deletion. The query now uses `query.iter(keys_only=True)`, which ignores the limit.

### Further bugfixes to bones

- **`BooleanBone`** never called `isInvalid()`/`vfunc` at all - custom validation functions were completely ignored.
- **`ColorBone`** accepted a `#` at any position within the string (instead of only leading) and crashed on non-string values.
- **`DateBone`**: the documented values `"now"`/`"nowX"` were never actually reached due to an incorrect check order.
- **`getDefaultValue()`** shared a single list instance across all languages of a multi-language `multiple` bone - appending to one language on one instance changed the default for every skeleton created afterwards.
- **`EmailBone`** accepted addresses that violate RFC 5321, such as `first..last@example.com` (double, or leading/trailing, dots in the local part).
- **`FileBone`** now validates when the bone is constructed whether all `refKeys` required for later checks (`mimetype`, `size`, `public`) are actually requested, instead of silently yielding `None` at runtime. `max_file_size` is now also exported in `structure()`.
- **`DateBone`** crashed with an unhandled `ValueError` (HTTP 500) on malformed input such as `"1.5"`, `"1-2"`, or `"12-"`.
- **`BooleanBone.refresh()`** crashed on a multi-language bone with no value set, and otherwise wrote the same default `dict` into every language; `setBoneValue()` now also honors `conf.bone_boolean_str2true`.
- **`StringBone`** only folded the uppercase `ẞ` during DIN 5007-2 normalization, not the lowercase `ß`.
- **`UidBone`** padded with `"*"` instead of `"0"`, and incorrectly counted the wildcard character towards the prefix length.
- **`RecordBone`** now raises a `ValueError` instead of a `TypeError` when `using` is missing.
- **`File.write()`**: the `weak` flag was inverted - a file in a folder received no blob lock and could be removed by the blob garbage collection, while a file without a repository stayed locked forever. The blob GC itself also stopped at the first already-marked blob instead of continuing with the rest.
- **`EmailBone.isInvalid()`** was restructured for readability, and address validation was consolidated (no behavior change).

viur-core's central JSON encoder/decoder (`viur.core.utils.json`) now also supports `decimal.Decimal` values directly and losslessly via a string representation, which nicely rounds off `NumericBone`'s decimal support. Along the way, a bug was fixed where certain falsy marker values (`b""`, `timedelta(0)`, `set()`) were not being decoded correctly.

## Modules

### `User.Status` is now an `IntEnum`

`user.Status` used to be a plain `Enum` with a manual comparison shim to allow it to be compared against raw integers. The problem: projects that extended `Status` with their own values ended up with two independent Enum classes that never compared equal, even for the same value. By switching to `enum.IntEnum`, values now compare via their plain integer value - even across project boundaries:

```py
class Status(enum.IntEnum):  # project-specific extension
    UNSET = 0
    ACTIVE = 10
    PENDING_REVIEW = 15  # custom addition, still comparable to core Status.ACTIVE
```

### Tree: only delete a node once its entire subtree is gone

Deletion of tree structures (`Tree`) has been reworked. Previously, the node itself was deleted synchronously right away, while removing the children was merely enqueued as a separate, deferred job. If that job was lost (e.g. due to queue cleanup or a crash), child nodes were left permanently pointing at an already-deleted parent.

Now the entire subtree deletion (all descendants first, leaf-wise from bottom to top, the node itself last) runs in a single deferred call, which can safely resume or be retried after an interruption. There is also a new, overridable `checkDeletePreconditions()` hook, which runs read-only over the whole subtree once before the actual deletion and can reject the entire operation (e.g. on a relation locked via `RelationalConsistency.PreventDeletion`), instead of aborting midway with a lock error.

### New `Email` module

There is now a standard module for managing sent emails: `EmailSkel` (kind `viur-emails`) stores sender, subject, body, recipients/CC/BCC, send status, and error count; the corresponding `Email` module provides predefined views for sent, unsent, and failed emails.

As with `File` and `History`, the module must be subclassed once per project:

```py
from viur.core.modules.email import Email

class Email(Email):
    pass
```

> [!IMPORTANT]
> The module requires two additional composite indexes on `viur-emails` (`isSend`+`errorCount desc` as well as `isSend`+`creationDate desc`), which need to be added to `index.yaml`.

![Email](email.png)

### `vi/routes` endpoint

A new endpoint `vi/routes` recursively returns all exposed routes of the system as a JSON array - intended as a debugging and security-scanning aid (e.g. for viur-crawler-style tools).

### `LoginKey` auth provider (`contrib`)

The new `contrib` package now includes a login mechanism via token/"magic link":

```py
class MyUser(User):
    authenticationProviders = [LoginKey, ...]
```

Login happens via a long, random token (`login_key`, at least 32 characters), which is filtered against. Failed attempts are limited to 12 per minute and IP.

> [!IMPORTANT]
> An indexed credential value is, in principle, enumerable by anyone with datastore read access. `LoginKey` should therefore only be used with sufficiently long, random tokens, and in a suitably secured environment.

### `RequestRateLimit` (`contrib`)

Also new in the `contrib` package: a global request rate limiter that already kicks in at the WSGI level, before routing and session handling:

```py
Router.requestValidators.append(
    RequestRateLimit(
        rate_for_guests=TimeWindow(limit=200, time_window=60),
        rate_for_users=TimeWindow(limit=500, time_window=60),
    )
)
```

Guests are identified by IP (IPv6 grouped into /64 blocks), authenticated users by their user key, each with its own quota backed by Memcache. Once exceeded, the endpoint returns HTTP 429 with a `Retry-After` header. This is separate from the pre-existing, datastore-backed `RateLimit` for individual actions.

### Admin configuration merged

The previously separate endpoints `vi/dumpConfig` (module tree + `conf.admin`) and `vi/get_settings` (public admin configuration) have been merged into a single `vi/get_config()`. The module tree is now only computed for users with `root`/`admin` rights. The response additionally contains `admin.language` and `admin.languages`.

### `@ResponseCache` (successor to `@enableCache`)

The previous `@enableCache` decorator has been completely reworked and renamed to `@ResponseCache`:

```py
@exposed
@ResponseCache(max_cache_time=datetime.timedelta(days=1))
def index(self):
    return f"Cached at {datetime.datetime.now()}"
```

New additions include, among others:

- Compression (gzip/zlib) of large cached responses
- Caching of redirects and response headers
- Restricting caching to specific renderers
- No more mandatory `urls` argument - if omitted, caching happens regardless of path

The previous mode constants (0-3) have been replaced by the descriptive `enum.IntEnum UserSensitive` (`IGNORE`, `GUEST_ONLY`, `BOTH`, `INDIVIDUAL`).

#### `FlushCacheTask`

The `@ResponseCache` cache can now also be cleared directly in the admin UI, via the maintenance functions - optionally filtered by path prefix or kind. The task is callable only by `root` users.

![FlushCacheTask](flushcachetask.png)

### Lifecycle hooks for `Request`

There are now two new decorator hooks that let code hook into request processing before and after it runs:

```py
from viur.core import before_request, after_request

@before_request
def my_before_hook():
    ...

@after_request
def my_after_hook():
    ...
```

`before_request` runs before `_process()` (the session isn't loaded yet), `after_request` runs after `_process()` (the response has already been generated, the session saved, `current.user` still available), but still before the CORS headers are set. Exceptions raised in the hooks are not swallowed.

### Reporting-Endpoints security header

ViUR now supports the Reporting API's `Reporting-Endpoints` header, the successor to the deprecated CSP directive `report-uri`. Endpoints are named once and then referenced by several headers:

```py
from viur.core import securityheaders

securityheaders.set_reporting_endpoint("csp", "/cspReport")
securityheaders.addCspRule("report-to", "csp", "enforce")
```

New is `conf.security.reporting_endpoints`, which maps the configured endpoints to their URLs; at startup, the configuration is validated and a warning is issued for any endpoints that won't work. The older `report-uri` remains useful for browsers without Reporting-API support, and is simply ignored by modern browsers once `report-to` is present.

### Creating security keys in batches

`securitykey.create()` now accepts an `amount` argument (maximum 500), to create multiple CSRF security keys in a single `db.put()` instead of in a loop with one `put()` per key:

```py
keys = securitykey.create(amount=10)  # tuple[str] instead of str
```

The JSON renderer endpoint `render.json.skey()` now also uses this batched creation.

### Further bugfixes

- **`List.view`** did not honor `allow_client_defined`, even though `List.index`, `List.structure`, `List.list`, and `List.preview` already did.
- **`cloudfunction_thumbnailer`**: fix in filename verification.
- **`ModuleConf.read_all_modules`** overwrote existing `ModuleConf` entries instead of preserving them.
- An import cycle when directly importing `viur.core.skeleton` (without importing `viur.core` first) was fixed; `ViURTestCase` tests also no longer share request/session context variables across test cases.
- `make_deferred` now honors `_call_deferred=False` even when no task queue is reachable.

## Internationalization (i18n)

### Fallback languages

`conf.i18n.fallback_languages` (default: empty list) now allows defining fallback languages that are tried in order when no translation exists for the requested language - only after that does `default_text` kick in.

```py
conf.i18n.fallback_languages = ["en", "de"]
```

Along the way, an inconsistency was fixed: previously, the Jinja path treated an empty translation as "present," while the Python path already treated that as "not present." Both paths now use the same rule.

### Pluggable translation sources

The two previously hardcoded sources for translations (the static `languages` module and a datastore query) can now be swapped or extended via `conf.i18n.sources`:

```py
conf.i18n.sources = [StaticModuleSource(), DatastoreSource(), MyCustomSource()]
```

Each source implements just one `load()` method. Sources are loaded in order, with a later source overwriting an earlier one's values per key. If `conf.i18n.sources` is not set, the same two previous default sources continue to be used.

This makes it possible, for example, to keep translations in Python code, in the database, or both.

## Architecture Decision Records (ADRs)

There are now Architecture Decision Records (ADRs) for core bones and key components, under `docs/adr/`, documenting the design decisions that were made (e.g. `docs/adr/bones/base.md`, `docs/adr/bones/captcha.md`, `docs/adr/bones/color.md`, and many more). Along the way, numerous smaller defects collected in `docs/known_bugs.md` were also worked through and fixed (see the bugfix lists above).

## Deprecations / Breaking Changes

### `History` module: kind name changed

The `History` module introduced in viur-core 3.8 initially stored its entries under the kind `viur-history`. To reduce the number of `viur-*`-prefixed kinds (this prefix is actually meant for purely technical, freely recreatable data such as `viur-relations`), the kind is now simply called `history` - analogous to `file` and `user`.

> [!IMPORTANT]
> Projects that already had the `History` module in production use before this change should check, before updating, whether a migration of existing `viur-history` records to the new kind `history` is necessary.

### `/vi/getStructure` deprecated

The endpoint `/vi/getStructure` is marked as deprecated (but still works) and should be replaced by `/vi/{module}/structure/{skel}`.

### `/vi/getVersion` and `/vi/settings` deprecated

Due to the merging of the admin configuration (see above), the version information now travels as a `"version"` property in the response of `/vi/config`. `/vi/getVersion` and `/vi/settings` remain as backward-compatible wrappers, but are marked as deprecated.

> [!IMPORTANT]
> Along the way, a bug was fixed: `/vi/getVersion` was previously not callable at all by non-privileged users, by mistake, since the endpoint was missing from the allowlist of unauthenticated vi routes.

### `conf.valid_application_ids` now uses `fnmatch`, and is generally optional

At startup, `conf.valid_application_ids` is no longer checked against the project ID via an exact string comparison, but via `fnmatch`. This makes it possible to enter glob patterns such as `"myproject-*"`, to cover multiple environments/deployments with a single entry, instead of having to list every project ID individually.
