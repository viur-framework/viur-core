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

Which timezone is right depends on what the value means, and that is a
project decision. A theatre site in Berlin has both kinds:

- the programme - "concert, 03.10., 19:30" is 19:30 *at the venue*, for every
  visitor, also for one from Tokyo planning a trip;
- the news blog - "posted 03.10., 19:30" may follow the reader's clock.

The bone itself only guesses. The same stored instant, 2026-10-03 17:30 UTC,
rendered straight from a `localize` bone:

| Request from                     | Rendered           |
|----------------------------------|--------------------|
| Germany (`DE`)                   | 03.10. 19:30       |
| Japan (`JP`)                     | 04.10. 02:30       |
| USA (`US` -> `EST`)              | 03.10. 12:30       |
| no header (task, health check)   | 03.10. 17:30 (UTC) |

Venue time is applied in the project, no core change needed:

- **Output:** convert in the template. A filter covers a fixed zone and a zone
  *per entity* (stages in Berlin and Vienna):

  ```py
  @jinjaGlobalFilter
  def in_timezone(render, value: datetime | None, timezone: str) -> datetime | None:
      return value.astimezone(pytz.timezone(timezone)) if value else None
  ```
  ```jinja
  {{ (skel.start|in_timezone("Europe/Berlin")).strftime("%d.%m. %H:%M") }}
  {{ (skel.start|in_timezone(skel.venue.dest.timezone)).strftime("%H:%M") }}
  ```

  The output no longer depends on the request, so a cached page stays one
  entry (see [../cache](../cache.md)).
- **Input:** only naive values are localized. A client that submits ISO with
  offset (`2026-10-03T19:30:00+02:00`) is stored as 17:30 UTC wherever the
  editor sits. Naive input (`03.10.2026 19:30`) is read in the editor's guessed
  zone - from New York that stores 2026-10-04 00:30 UTC, i.e. 02:30 in Berlin.
  To pin input *and* output of one bone, override `guessTimeZone` to return a
  fixed zone.
- **Reader time:** render `<time datetime="{{ value.isoformat() }}">` and format
  it in the browser with `Intl.DateTimeFormat` - one cache entry, and the reader
  also gets their own date format. Server-side reader time needs a cache entry
  per zone; see [../cache](../cache.md).

Name zones the IANA way (`Area/City`, as known to `pytz`), not by offset:

| Zone                  | Offset Jan / Jul | Note                          |
|-----------------------|------------------|-------------------------------|
| `"Europe/Berlin"`     | +01:00 / +02:00  |                               |
| `"Europe/London"`     | +00:00 / +01:00  |                               |
| `"America/New_York"`  | -05:00 / -04:00  | not `"EST"`, see Traps        |
| `"Asia/Tokyo"`        | +09:00 / +09:00  | no DST                        |
| `"Asia/Kolkata"`      | +05:30 / +05:30  | half-hour offset              |
| `"Australia/Sydney"`  | +11:00 / +10:00  | southern hemisphere: DST in Jan |
| `"UTC"`               | +00:00 / +00:00  | technical times               |

A place follows daylight saving time and future rule changes (the tz database
and `pytz` ship them), an offset does not: with a fixed +02:00 a December
concert stored as 18:30 UTC renders as 20:30. The names are also what browsers
(`Intl.DateTimeFormat` `timeZone`), `zoneinfo`, databases and iCalendar (`TZID`)
use, so frontend and backend can share one value. `pytz.timezone()` rejects
offsets like `"+2"` or `"UTC+2"`.

`singleValueFromClient` accepts POSIX timestamps, `now`/`now<seconds>`, ISO,
US and EU formats - the docstring lists them all.

## Rules
- `creationMagic` / `updateMagic` are deprecated; use `compute` with
  `ComputeMethod.Once` / `OnWrite` instead (that is what `Skeleton.creationdate`
  and `changedate` do).
- Serialized values are always timezone-aware - `singleValueSerialize` asserts
  it and refuses to save a naive datetime (a `naive` bone gets UTC attached).
- The year must be >= 1900 because `strftime` breaks below that.
- `now` and `now<seconds>` are only accepted when both `date` and `time` are
  set; on a date-only or time-only bone they are `Invalid`.
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
- The parsing branches are ordered and the `now` branch sits before the
  time-only one, deliberately - otherwise `now` would fall through into the
  time parser instead of being answered.
- `buildDBFilter` calls `self.fromClient(resDict, key, rawFilter)` with a
  plain dict as skeleton and the *filter key* (`date$lt`) as bone name. It
  works, but any override of `fromClient` - and the `after_from_client` hook it
  calls - has to survive being called that way.
- `guessTimeZone` returns `None` for `naive` bones, so anything calling it and
  expecting a tzinfo must handle None.
- `guessTimeZone` falls back to UTC silently and often: no
  `X-Appengine-Country` header (task queue, cron, tests, health checks), an
  unknown country code, or a country with several timezones and no hand-picked
  fallback (CA, BR, RU, ...). Nothing is logged.
- Every request from the US is mapped to `EST`, a fixed UTC-05:00 without DST.
  During summer time guessed values for US visitors are one hour off.
- The sign of the `Etc/GMT` zone names is inverted (POSIX convention):
  `"Etc/GMT-2"` is UTC+2. They never follow DST.
- `compute` functions run inside the request and see the localized value.
  `skel["date"].year` of an instant near midnight differs between a request
  from Germany and a deferred task (UTC) - a computed `year` bone can drift.
- Every skeleton inherits `creationdate`/`changedate` as localized
  `DateBone`s. A response that renders a full skeleton (JSON views) therefore
  depends on the guessed timezone even if the project's own dates do not -
  their ISO offset differs.
- Microseconds are always dropped, on read from client and on serialize.
- `structure()` does not export `localize`, so the frontend cannot tell a
  localized bone from a UTC one.

## See also
[base](base.md), [../skeleton](../skeleton.md)
