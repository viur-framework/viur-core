---
covers: [viur.core.email.EmailTransport, viur.core.email.send_email, viur.core.email.send_email_deferred]
status: accepted
---
## Seam
Own delivery service: subclass `EmailTransport`, implement `deliver_email`,
and assign an **instance** to `conf.email.transport_class`. Optional overrides:
`validate_queue_entity` (runs before the mail is queued),
`transport_successful_callback` (tracking), `max_retries`; helpers you get for
free are `split_address`, `validate_attachment` and `fetch_attachment`.

`send_email()` is the only entry point for application code; it renders through
`conf.emailRenderer`, writes a `viur-emails` entity and defers
`send_email_deferred` into the `viur-emails` queue.

## Rules
- `deliver_email` must raise on failure. Returning normally marks the mail as
  sent, irreversibly.
- `transport_class` must be an instance, not the class (send_email raises with
  exactly that hint).
- The queue entity carries body and attachments and must stay below the
  datastore entity limit (~1 MB). Large files belong in an attachment with
  `file_key` or `gcsfile`; those are fetched later inside the deferred task.
- The project needs a dedicated `viur-emails` Cloud Tasks queue with a large
  backoff (see the module docstring for a `queue.yaml` snippet).
- Either `tpl` or `stringTemplate`, never both (ValueError).

## Traps
- On the development server `send_email` returns False without sending unless
  `conf.email.send_from_local_development_server` is set. The second condition
  meant to always skip `EmailTransportAppengine` there compares an instance
  with the class (`transport_class is EmailTransportAppengine`) and is
  therefore never true - do not rely on it.
- `conf.email.recipient_override` rewrites all recipients and clears cc/bcc; a
  leading `@` turns it into a suffix-rewrite of the original address. The
  value `False` disables sending entirely.
- The datastore turns empty lists/dicts into `None`. `send_email_deferred`
  compensates with `or []` before calling `deliver_email` - own code reading
  the queue entity must do the same.
- `errorCount` is incremented and stored *before* the exception is re-raised,
  so retries are counted across queue retries; exceeding `max_retries` raises
  `ChildProcessError`.
- `validate_queue_entity` runs before `db.put`, so an invalid attachment fails
  the caller's request - not the background task.
- Sent mails stay in the datastore until `clean_old_emails_from_log` (daily,
  `conf.email.log_retention`) removes them. Body, attachments and context are
  excluded from indexes but still readable.
- `send_email_to_admins` falls back to querying users with `access = root`
  when `conf.email.admin_recipients` is unset - on a fresh instance that can
  be nobody, and it only logs `critical`.

## Why not
Subject and body are not parameters: `conf.emailRenderer` (the html render's
`renderEmail`) uses the first non-empty line of the template as the subject and
the rest as the body. A transport therefore never composes a subject itself.

## See also
[tasks](tasks.md), [render](render.md), [config](config.md)
