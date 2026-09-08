# Known bugs

Found while reading the code for the seam documentation in `docs/adr/`.
Everything listed here is still open; fixed entries are removed from this file.

The first pass covered the framework seams (skeleton, module, tasks, email,
file module, ...), the second pass every bone type under
`src/viur/core/bones/`.

Each entry: what is wrong, what it costs, what the fix would be.

## Dead code paths

### `src/viur/core/modules/file.py` - `download` without a signature cannot work

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

### `src/viur/core/modules/file.py` - `File.write(rootnode=...)` is ignored

`write()` only enters the repository branch `if folder:`. Passing a *rootnode*
without a *folder* therefore falls into the `else` and the file is stored with
`parentrepo = None` - although the docstring promises "If only *rootnode* is
set, the file is added to that repository in the root folder". Combined with
the (now correct) `weak` flag such a file is written as a weak file.

The parameter is also annotated `t.Optional[db.Key]`, while the code reads
`rootnode.key`. A `db.Key` has no `.key`, so the annotated type raises
`AttributeError` in folder mode; only the `db.Entity` that
`ensureOwnModuleRootNode()` returns actually works.

Fix: enter the repository branch for `folder or rootnode`, and accept a
`db.Key` as documented.

## Minor

### `src/viur/core/db/query.py` - three methods break on an unsatisfiable query

`queries is None` is the documented "unsatisfiable" state, and `filter`,
`order`, `limit`, `distinctOn` and `or_filter` treat it as a no-op. Three
methods do not:

- `getCursor()` assigns `q` only in the `QueryDefinition` and `list` branches,
  so the final `return` reads an unbound `q` (`UnboundLocalError`). An empty
  query list hits this too.
- `setCursor()` ends up on `assert isinstance(self.queries,
  QueryDefinition)` - `AssertionError`, and an `AttributeError` under
  `python -O`.
- `get_orders()` raises `ValueError` for anything that is neither a
  `QueryDefinition` nor a list.

`mergeExternalFilter` reaches the first of these on its own: the fulltext
branch sets `queries = None` without returning and the cursor handling below it
then calls `setCursor`, so `?search=…&cursor=…` against a module without a
fulltext adapter is an HTTP 500.

Fix prompt: `docs/superpowers/plans/2026-09-03-query-unsatisfiable-cursor-methods.md`
in the ag-dev repo.

## Bones: contract violations

### `src/viur/core/bones/password.py` - `isInvalid` returns a list

`PasswordBone.isInvalid` returns `tests_errors`, a list of hint strings, where
every other bone returns a single message or None. `ReadFromClientError.
errorMessage` then holds a list, which anything formatting that message has to
special-case.

Fix: join the hints, or document the list as part of the contract.

### `src/viur/core/bones/spatial.py` - `getEmptyValue` contradicts its docstring

The docstring explains that `(91.0, 181.0)` is used as an out-of-range marker
for "empty", the code returns `(0.0, 0.0)`. For any region containing the
origin, a legitimately entered `0, 0` is reported empty by `isEmpty` and
dropped.

Fix: return the documented marker, or correct the docstring and accept that
`0, 0` cannot be stored. Changes the meaning of already stored values, so it
needs a decision rather than a patch.

### `src/viur/core/bones/credential.py` - `unserialize` returns a dict

`CredentialBone.unserialize` returns `{}` where the `BaseBone` contract asks
for a bool, and never touches `skel.accessedValues`. The effective behaviour
(value reads as None) is intended; the signature is not.

### `src/viur/core/bones/key.py` - two different key parsers

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

## Deprecation shims that do nothing

### `src/viur/core/bones/file.py` and `src/viur/core/skeleton/tasks.py`

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

## Won't fix

### `src/viur/core/bones/date.py` - creation/update magic does not lock the bone

```python
self.readonly = True  # the attribute is readOnly
```

This assignment creates an unrelated `readonly` attribute, so a
`DateBone(creationMagic=True)` stays writable and a client can overwrite the
automatic timestamp through add/edit.

Decided against fixing: the magic is deprecated (it warns with a
`DeprecationWarning` and is documented as such) and no longer used - repairing
the lock now would only change behaviour for the projects that still rely on
the broken state. Use `compute` instead. Goes away with VIUR4.

## Bones: minor / inconsistencies

- `src/viur/core/bones/select.py:74-113` - `values` is re-evaluated in
  `__getattribute__` on *every* access, rebuilding one `translate` object per
  option. `singleValueFromClient` iterates it per request.

## Unverified

### `src/viur/core/email.py` - decorator order on `check_sib_quota`

```python
@PeriodicTask(interval=datetime.timedelta(hours=1))
@staticmethod
def check_sib_quota() -> None:
```

`PeriodicTask` receives the `staticmethod` object and assigns
`fn.periodicTaskName` to it. Whether that assignment is accepted depends on the
Python version. Not tested - listed only so someone checks it against the
supported versions.
