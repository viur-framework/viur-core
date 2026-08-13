---
covers: [viur.core.bones.date.DateBone]
status: accepted
---
## Seam
`DateBone` stores a `datetime`. Four flags decide its semantics:

- `date` / `time` - which parts are meaningful (at least one required). The
  unused part is zeroed on serialize (`time=False` -> 00:00:00,
  `date=False` -> 1970-01-01).
- `localize` - interpret input and output in the *user's* timezone; only valid
  with `date and time`, and the default when neither `localize` nor `naive` is
  given.
- `naive` - store and hand out naive datetimes; mutually exclusive with
  `localize`.

The timezone is guessed per request in `guessTimeZone` from the
`X-Appengine-Country` header (with hand-picked fallbacks for US, DE, AU) and
cached in `current.request_data`. On a development server the header is never
looked at - the local system timezone (`tzlocal`) wins instead, so localized
values differ between a local run and production. Override that method to plug
in a real user timezone.

`singleValueFromClient` accepts POSIX timestamps, `now`/`now<seconds>`, ISO,
US and EU formats - the docstring lists them all.

## Rules
- `creationMagic` / `updateMagic` are deprecated; use `compute` with
  `ComputeMethod.Once` / `OnWrite` instead (that is what `Skeleton.creationdate`
  and `changedate` do).
- Serialized values are always timezone-aware - `singleValueSerialize` asserts
  it and refuses to save a naive datetime (a `naive` bone gets UTC attached).
- The year must be >= 1900 because `strftime` breaks below that.
- Do not compare values from a `localize` bone across requests: the same
  stored instant is handed out in different timezones depending on the caller.

## Traps
- `creationMagic`/`updateMagic` assign `self.readonly = True` - lowercase.
  The real attribute is `readOnly`, so the bone stays writable and a client can
  overwrite the "magic" value through add/edit.
- Input like `"1.5"` passes the digit check (the dot is stripped for the test)
  and then hits `int(value)`, which raises an uncaught ValueError - a 500
  instead of a validation error.
- Timestamps are only accepted between `-2**30` and `2**31-2`, everything else
  becomes `Invalid`. A date beyond 2038 cannot be set as a POSIX timestamp,
  although the bone stores it happily when it arrives in any other format.
- The parsing branches are ordered, and the time-only branch
  (`not self.date and self.time`) sits before the `now` branch. On a
  `DateBone(date=False)` the documented `now` therefore never matches and is
  rejected as invalid.
- The `now` offset requires `len(value) > 4`, so `"now5"` silently means "now",
  while `"now10"` adds ten seconds.
- `buildDBFilter` calls `self.fromClient(resDict, key, rawFilter)` with a
  plain dict as skeleton and the *filter key* (`date$lt`) as bone name. It
  works, but any override of `fromClient` - and the `after_from_client` hook it
  calls - has to survive being called that way.
- `guessTimeZone` returns `None` for `naive` bones, so anything calling it and
  expecting a tzinfo must handle None.
- Microseconds are always dropped, on read from client and on serialize.
- `structure()` does not export `localize`, so the frontend cannot tell a
  localized bone from a UTC one.

## See also
[base](base.md), [../skeleton](../skeleton.md)
