# Known bugs

Found while reading the code for the seam documentation in `docs/adr/`, at tag
`v3.8.33`. Nothing in this list has been fixed. Line numbers refer to that tag.

The first pass covered the framework seams (skeleton, module, tasks, email,
file module, ...), the second pass every bone type under
`src/viur/core/bones/`.

Each entry: what is wrong, what it costs, what the fix would be.

## Broken comparisons and type checks

### `src/viur/core/email.py:403` - dev-server guard never triggers

```python
if not conf.email.send_from_local_development_server or transport_class is EmailTransportAppengine:
```

`transport_class` is an *instance* (`conf.email.transport_class`), so
`is EmailTransportAppengine` is always False. The intent - never deliver
through the App Engine Mail API from a local development server - is not
enforced: with `send_from_local_development_server = True` the call goes
through and fails inside the API instead.

Fix: `isinstance(transport_class, EmailTransportAppengine)`.

### `src/viur/core/email.py:579` - Brevo quota check never runs

```python
if not isinstance(conf.email.transport_class, EmailTransportSendInBlue):
    return  # no SIB key, we cannot check
```

`EmailTransportSendInBlue` is the *deprecated subclass* of
`EmailTransportBrevo`. A project configured correctly with
`EmailTransportBrevo()` fails this check, so `check_sib_quota` returns
immediately and the credit warning emails are never sent.

Fix: check against `EmailTransportBrevo`.

### `src/viur/core/i18n.py:651` - swapped `isinstance` arguments

```python
if not isinstance(dict, entity["translation"]):
```

Arguments are the wrong way round; this raises
`TypeError: isinstance() arg 2 must be a type` instead of validating. It sits
in `migrate_translation`, which is *not* deferred and not retried (those
decorators belong to `add_missing_translation`): `DatastoreSource.load` calls
it synchronously for every translation entity without a `name`, and
`initializeTranslations` re-raises whatever a source throws. A single
unmigrated entity that still carries a `translation` field therefore takes the
whole instance down at startup.

Fix: `isinstance(entity["translation"], dict)`.

## Wrong values

### `src/viur/core/modules/file.py:900` - `weak` flag inverted in `File.write()`

```python
fileskel["weak"] = bool(parentrepokey)
```

The docstring of `File.write` says a file without folder and rootnode is added
as a *weak* file, and `File.add` uses `skel["weak"] = rootNode is None`. Here
it is the other way round: files written into a repository are marked weak,
files without one are not.

Consequences follow `FileLeafSkel.preProcessBlobLocks`, which only locks the
`dlkey` when the file is *not* weak: a file written into a folder gets no blob
lock and can be collected by the blob GC, while a repository-less file is
locked forever.

Fix: `fileskel["weak"] = not parentrepokey`.

### `src/viur/core/bones/base.py:123` - single error is dropped

```python
if isinstance(errors, ReadFromClientError):
    errors = (ReadFromClientError, )
```

The tuple holds the *class*, not the instance. The `isinstance` filter on the
next lines removes it again, `self.errors` ends up empty and the constructor
raises `ValueError("ReadFromClientException requires for at least one
ReadFromClientError")`. Passing a single `ReadFromClientError` - which the
docstring explicitly allows - is therefore impossible.

Fix: `errors = (errors, )`.

## Control flow

### `src/viur/core/modules/file.py:1489` - GC run aborts instead of skipping

In `doCheckForUnreferencedBlobs`, when a stale blob is already marked for
deletion the loop does `return` instead of `continue`, so the whole run ends
and the remaining `viur-blob-locks` entries of this batch (and every following
cursor batch) are not processed. Cleanup then only progresses on the next
periodic call, and only until it hits an already-marked blob again.

Fix: `continue`.

### `src/viur/core/tasks.py:421` - retry notification mail always fails

```python
stringTemplate=string_template if tpl is None else string_template,
```

Both branches are identical, so `stringTemplate` is always passed. When
`retry_n_times(..., tpl="...")` is used, `send_email` receives `tpl` *and*
`stringTemplate` and raises `ValueError` on its xor check. The surrounding
`except Exception` swallows it, so the "task failed permanently" mail is
silently lost - exactly in the situation it exists for.

Fix: pass `stringTemplate` only when `tpl is None`.

## Dead code paths

### `src/viur/core/modules/file.py:1086-1109` - `download` without a signature cannot work

The unsigned branch is documented as the root / `file-view` path: "blobKey is
then the path inside cloudstore - not a base64 encoded tuple". But the blobKey
is base64-decoded and split on `\0` *before* the branch is reached, and the
branch itself then looks up the wrong value:

- a raw storage path (`abc123/source/foo.jpg`) is decoded by
  `urlsafe_b64decode` into garbage (Python only validates with
  `validate=True`), `.decode("UTF-8")` raises `UnicodeDecodeError` - a
  `ValueError` subclass - and the caller gets `BadRequest` before any
  permission is checked;
- a properly signed payload passed without `sig` decodes fine, but then
  `bucket.get_blob(blobKey)` searches for the base64 string as the blob name
  instead of `dlPath`, finds nothing and raises `Gone`.

So a root user or a user with `file-view` cannot download a blob through this
endpoint at all.

Fix prompt: `docs/superpowers/plans/2026-09-03-file-download-without-signature.md`
in the ag-dev repo.

### `src/viur/core/bones/uid.py:22` - the `CollisionError` retry is dead code

```python
for i in range(3):
    try:
        ...
        db.put(db_obj)
        break
    except db.CollisionError:  # recall the function
        time.sleep(i + 1)
else:
    raise ValueError("Can't set the Uid")
```

`db.CollisionError` does not exist. The symbol came from `viur.datastore` and
disappeared with the re-integration of the Google Datastore API (#1431);
`src/viur/core/db/__init__.py` no longer exports it. Python only evaluates the
`except` expression once something is raised inside the `try`, and then the
original exception is replaced by `AttributeError: 'super' object has no
attribute 'CollisionError'`.

So the retry never runs, `time.sleep` is unreachable, the `else` branch of the
loop cannot raise its `ValueError`, and every real datastore error is masked
as an `AttributeError`.

Even if the symbol existed the retry would be pointless: `serialize_compute`
runs inside the skeleton's write transaction (`skeleton/skeleton.py:421`), so
retrying inside the transaction body cannot resolve a conflict that only
surfaces on commit - and sleeping there blocks the request. The commit
conflict is already handled by `db.run_in_transaction`
(`db/transport.py:166-178`).

Fix: drop the loop and let the conflict propagate to the surrounding
`run_in_transaction`.

### `src/viur/core/modules/file.py:767` - `create_src_set` on a multi-language bone

```python
if not language or not (file := cls.get(language)):
```

`cls` is `File`; neither `File` nor `Module` defines `get`, so this raises
`AttributeError` for every `LanguageWrapper` value - i.e. for every FileBone
with `languages` set.

Fix: `file.get(language)`.

## Minor

### `render/json/__init__.py:6` and `skeleton/__init__.py:53` - `__all__` holds objects, not names

```python
__all__ = [default]                            # render/json
__all__ = [ABSTRACT_SKEL_CLS_SUFFIX, BaseSkeleton, DatabaseAdapter, ...]  # skeleton
```

`__all__` must contain strings, so `import *` fails on both:

    from viur.core.render.json import *
    -> TypeError: Item in viur.core.render.json.__all__ must be str, not ABCMeta
    from viur.core.skeleton import *
    -> TypeError: Item in viur.core.skeleton.__all__ must be str, not MetaBaseSkel

It goes unnoticed because the core only ever imports these packages as
modules. In the skeleton list the first entry is a string by accident -
`ABSTRACT_SKEL_CLS_SUFFIX` is `"AbstractSkel"`, the *value* rather than the
symbol name, so even fixing the other entries would leave a name that does
not exist.

Fix: list the names as strings.

### `src/viur/core/prototypes/skelmodule.py:171` - `_apply_default_order` docstring contradicts the code

```python
The `default_order` will only be applied when the query has no other order, or is on a multquery.
```

The code does the opposite of the second half: a multi-query is explicitly
excluded (`not isinstance(query.queries, list)`), so `default_order` is
applied only to a single query. "multquery" is a typo as well, and the third
condition (no `search` parameter in the request) is not mentioned at all.

Fix: "... only be applied when the query has no other order, is not a
multi-query and no `search` parameter was sent."

### `src/viur/core/db/query.py:485-526` - three methods break on an unsatisfiable query

`queries is None` is the documented "unsatisfiable" state, and `filter`,
`order`, `limit`, `distinctOn` and `or_filter` treat it as a no-op. Three
methods do not:

- `getCursor()` assigns `q` only in the `QueryDefinition` and `list` branches,
  so the final `return` reads an unbound `q` (`UnboundLocalError`). An empty
  query list hits this too.
- `setCursor()` (query.py:429-457) ends up on `assert isinstance(self.queries,
  QueryDefinition)` - `AssertionError`, and an `AttributeError` under
  `python -O`.
- `get_orders()` raises `ValueError` for anything that is neither a
  `QueryDefinition` nor a list.

`mergeExternalFilter` reaches the first of these on its own: the fulltext
branch sets `queries = None` without returning (query.py:192) and the cursor
handling below it then calls `setCursor` (query.py:219), so
`?search=…&cursor=…` against a module without a fulltext adapter is an
HTTP 500.

Fix prompt: `docs/superpowers/plans/2026-09-03-query-unsatisfiable-cursor-methods.md`
in the ag-dev repo.

### `src/viur/core/securityheaders.py:159` - `extendCsp` assumes a policy exists

`conf.security.content_security_policy` may legitimately be `None` (the type
hint says `t.Optional`), which makes the `.get("enforce")` raise
`AttributeError`. Note the error page calls `extendCsp` for its style nonce,
so this turns an error response into a second error.

## Bones: validation that does not validate

### `src/viur/core/bones/spatial.py:269,273` - invalid geo filter is ignored

```python
dbFilter.datastoreQuery = None
```

Both error paths in `SpatialBone.buildDBFilter` (unparseable lat/lng, and
coordinates outside the configured bounds) try to make the query
unsatisfiable. `db.Query` has no `datastoreQuery` attribute - the correct one
is `queries` - so this only creates a new, unused attribute. The query then
runs **without the spatial constraint** and returns everything the remaining
filters allow, instead of nothing.

Fix: `dbFilter.queries = None`.

### `src/viur/core/bones/uri.py:56` - a protocol string becomes a character set

```python
if not isinstance(self.accepted_protocols, Iterable) or isinstance(self.accepted_protocols, str):
    self.accepted_protocols = set(self.accepted_protocols)
```

For a plain string, `set("https")` yields `{"h", "t", "p", "s"}`. So
`UriBone(accepted_protocols="https")` allows the protocols `h`, `t`, `p` and
`s` - and rejects `https`. The whole restriction is silently inverted.

Two lines later the same parameter is checked for the wildcard - on the
original argument, not on the normalized one:

```python
if "*" in accepted_protocols:
    self.accepted_protocols = None
```

For a list this is a membership test, for a string a substring test. Any
string containing a `*` therefore switches the protocol check off entirely:
`UriBone(accepted_protocols="http*")` accepts `file://x`. Since fnmatch
patterns are a documented and tested way to write this option, that spelling
is the obvious one to reach for.

Fix: normalize the str case to `{self.accepted_protocols}` first, then test
the wildcard against the normalized set.

### `src/viur/core/bones/uri.py:145` - default ports are rejected

```python
if not any(parsed_url.port in rng for rng in self.accepted_ports):
```

`urlparse(...).port` is `None` when the URL relies on the scheme default, so
with `accepted_ports=(443,)` the valid `https://example.com` is rejected. A
malformed port additionally makes the property itself raise `ValueError`,
which `isInvalid` does not catch - that becomes a 500 rather than a validation
error.

Fix: map a missing port to the scheme default before the check, and guard the
`ValueError`.

### `src/viur/core/bones/date.py:80` - creation/update magic does not lock the bone

```python
self.readonly = True  # todo: why???
```

The attribute is `readOnly`. This assignment creates an unrelated `readonly`
attribute, so a `DateBone(creationMagic=True)` stays writable and a client can
overwrite the automatic timestamp through add/edit. (The magic itself is
deprecated in favour of `compute`.)

Fix: `self.readOnly = True` - or drop the magic and use `compute`.

## Bones: uncaught exceptions on client input

### `src/viur/core/bones/date.py:125-126` - `"1.5"` raises instead of failing validation

```python
if value.replace("-", "", 1).replace(".", "", 1).isdigit():
    if int(value) < -1 * (2 ** 30) or int(value) > (2 ** 31) - 2:
```

The digit test strips one dot, so `"1.5"` is considered a timestamp - but
`int("1.5")` then raises `ValueError`, uncaught. Any client can turn a date
field into a 500.

Fix: convert with `float(value)` (the value is passed to `fromtimestamp` as a
float anyway) or catch the ValueError.

### `src/viur/core/bones/randomslice.py:36` - `NotImplemented` is not an exception

```python
raise NotImplemented("A RandomSliceBone must not visible and readonly!")
```

`NotImplemented` is a singleton, not an exception class, so this raises
`TypeError: exceptions must derive from BaseException` and the intended message
is lost.

Fix: `raise NotImplementedError(...)`.

### `src/viur/core/bones/record.py:124,145` - missing None guard in the write path

`RecordBone.postSavedHandler` and `postDeletedHandler` iterate
`value.items()` for every entry, while `getSearchTags` and
`getReferencedBlobs` guard the same loop with `if value is None: continue`. A
stored `null` inside a `multiple` record therefore raises `AttributeError`
during save or delete.

Fix: add the same guard.

## Bones: contract violations

### `src/viur/core/bones/numeric.py:160-162` - missing comma in the error message

```python
i18n.translate(
    "core.bones.error.minmax"
    "Value not between {{min}} and {{max}}",
```

Two adjacent string literals are concatenated, so the translation *key*
becomes `core.bones.error.minmaxValue not between {{min}} and {{max}}` and
there is no default text. The min/max error can never be translated, and
`add_missing_translations` records the garbage key.

Fix: insert the comma.

### `src/viur/core/bones/password.py:115` - `isInvalid` returns a list

`PasswordBone.isInvalid` returns `tests_errors`, a list of hint strings, where
every other bone returns a single message or None. `ReadFromClientError.
errorMessage` then holds a list, which anything formatting that message has to
special-case.

Fix: join the hints, or document the list as part of the contract.

### `src/viur/core/bones/spatial.py:390` - inverted type check in `setBoneValue`

```python
if not isinstance(value, (tuple, list)) and len(value) == 2:
    raise ValueError("Value must be a tuple or a list of (lat, lng)")
```

The `and` should reject "not a sequence **or** not of length 2". As written a
3-element tuple passes unchecked while the 2-character string `"ab"` raises.
The method also returns `None` instead of the documented bool, so callers see
"failed".

Fix: `if not isinstance(value, (tuple, list)) or len(value) != 2:` and
`return True` at the end.

### `src/viur/core/bones/spatial.py:214` - `getEmptyValue` contradicts its docstring

The docstring explains that `(91.0, 181.0)` is used as an out-of-range marker
for "empty", the code returns `(0.0, 0.0)`. For any region containing the
origin, a legitimately entered `0, 0` is reported empty by `isEmpty` and
dropped.

Fix: return the documented marker, or correct the docstring and accept that
`0, 0` cannot be stored.

### `src/viur/core/bones/credential.py:59-71` - `unserialize` returns a dict

`CredentialBone.unserialize` returns `{}` where the `BaseBone` contract asks
for a bool, and never touches `skel.accessedValues`. The effective behaviour
(value reads as None) is intended; the signature is not.

### `src/viur/core/bones/key.py:139-176` - two different key parsers

`singleValueFromClient` parses with `db.normalize_key`/`db.key_helper`, while
`buildDBFilter._decodeKey` only accepts `db.Key.from_legacy_urlsafe`. A key
notation the bone happily *stores* can therefore raise RuntimeError when used
as a filter, which `mergeExternalFilter` turns into an empty result set.
`buildDBFilter` additionally returns `None` instead of the query when the bone
is not part of the filter.

An empty list is a third problem: `buildDBFilter` sets `dbFilter.queries = []`
before filling it, so a filter `{"key": []}` leaves the query as a multi-query
without a single sub-query. `Query.run()` then reads `self.queries[0].limit`
and raises `IndexError` before touching the datastore - an HTTP 500 on client
input, also reachable as `{"<bone>.dest.key": []}` through
`RelationalBone.buildDBFilter`. The correct state for an empty IN-list is
`queries = None`.

Fix prompt: `docs/superpowers/plans/2026-09-03-keybone-empty-in-list.md` in the
ag-dev repo.

### `src/viur/core/bones/record.py:172` - `getSearchDocumentFields` is dead

It calls `bone.getSearchDocumentFields(...)`, which no longer exists on
`BaseBone`. Any caller gets an AttributeError. Remove it or reimplement it on
the base class.

### `src/viur/core/bones/record.py:37` - wrong exception for a missing `using`

`issubclass(using, RelSkel)` runs before the None check, so `RecordBone()`
without `using` raises `TypeError: issubclass() arg 1 must be a class` instead
of the intended ValueError.

## Deprecation shims that do nothing

### `src/viur/core/bones/file.py:55` and `src/viur/core/skeleton/tasks.py:60`

```python
locals()[_new] = kwargs.pop(_dep)
```

Assigning into `locals()` has no effect inside a function. Both
`ensureDerived` (`srcKey`, `deriveMap`, `refreshKey`) and `update_relations`
(`changedBone`, `minChangeTime`, `destKey`) warn about the deprecated
parameter and then silently drop the value - the function continues with the
default. Callers still using the old names are quietly ignored.

Fix: rebind the real parameter explicitly, e.g. via a dict of resolved
arguments.

## Bones: minor / inconsistencies

- `src/viur/core/bones/boolean.py:109,111` - `setBoneValue` calls
  `utils.parse.bool(value)` without `conf.bone_boolean_str2true`, unlike every
  other path in the bone. Only differs for projects that override the config.
- `src/viur/core/bones/boolean.py:73` - `refresh` indexes `skel[name][lang]`
  for multi-language bones; raises TypeError while the value is still None.
- `src/viur/core/bones/string.py:278-286` - the DIN 5007-2 transformation maps
  `ẞ` but not `ß`, so lowercase sharp s is not folded to `ss`.
- `src/viur/core/bones/uid.py:56` - `fillchar` defaults to `"*"`, so padded
  uids look like `"***********0"`. Presumably `"0"` was meant.
- `src/viur/core/bones/select.py:74-113` - `values` is re-evaluated in
  `__getattribute__` on *every* access, rebuilding one `translate` object per
  option. `singleValueFromClient` iterates it per request.
- `src/viur/core/bones/randomslice.py:57` - `buildDBSort` still has the
  pre-`postfix` signature; it only works because all current callers pass four
  positional arguments.

## Unverified

### `src/viur/core/email.py:565-566` - decorator order on `check_sib_quota`

```python
@PeriodicTask(interval=datetime.timedelta(hours=1))
@staticmethod
def check_sib_quota() -> None:
```

`PeriodicTask` receives the `staticmethod` object and assigns
`fn.periodicTaskName` to it. Whether that assignment is accepted depends on the
Python version. Not tested - listed only so someone checks it against the
supported versions.
