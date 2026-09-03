---
covers: [viur.core.email.EmailTransport, viur.core.email.send_email,
         viur.core.email.send_email_deferred, viur.core.email.send_email_to_admins,
         viur.core.email.clean_old_emails_from_log, viur.core.email.normalize_to_list,
         viur.core.email.EmailTransportBrevo, viur.core.email.EmailTransportSendInBlue,
         viur.core.email.EmailTransportSendgrid, viur.core.email.EmailTransportSmtp,
         viur.core.email.EmailTransportAppengine]
status: accepted
---
## Seam
Own delivery service: subclass `EmailTransport`, implement `deliver_email`,
and assign an **instance** to `conf.email.transport_class`. Optional
overrides: `validate_queue_entity` (runs before the mail is queued),
`validate_attachment` (runs per attachment inside `send_email`),
`transport_successful_callback` (tracking). `split_address` and
`fetch_attachment` are helpers your `deliver_email` has to call itself.

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
  `file_key` or `gcsfile` - but `deliver_email` has to resolve them through
  `fetch_attachment`; the core hands them over untouched.
- `conf.email.sender_override` overrides a `sender` passed to `send_email`;
  `sender_default` only applies when none was given.
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
- `errorCount` is incremented and stored *before* the exception is re-raised.
  It is a diagnostic counter only - there is no retry cap in the core (it was
  removed in #1749), the backoff in `queue.yaml` decides.
- `send_email` validates recipients with `assert` (no address at all, a
  non-string or an empty string): an HTTP 500 instead of an error, and gone
  under `python -O`.
- `validate_queue_entity` runs before `db.put`, so an invalid attachment fails
  the caller's request - not the background task.
- Sent mails stay in the datastore until `clean_old_emails_from_log` (daily,
  `conf.email.log_retention`) removes them. It only queries `isSend = True`,
  so failed deliveries are never cleaned up. Body, attachments and context are
  excluded from indexes but still readable.
- `send_email_to_admins` falls back to querying users with `access = root`
  when `conf.email.admin_recipients` is unset - and only when the app has a
  `user` module. On a fresh instance that can be nobody, and it only logs
  `critical`. It counts a mail as successful as soon as `send_email` was
  called, so a `False` return (dev server, `recipient_override=False`) stays
  silent.

## Why not
Subject and body are not parameters: `conf.emailRenderer` (the html render's
`renderEmail`) uses the first non-empty line of the template as the subject and
the rest as the body. A transport therefore never composes a subject itself.

## See also
[tasks](tasks.md), [render](render.md), [config](config.md)
