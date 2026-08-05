---
covers: [viur.core.tasks.CallDeferred, viur.core.tasks.PeriodicTask, viur.core.tasks.retry_n_times, viur.core.tasks.QueryIter, viur.core.tasks.CustomEnvironmentHandler, viur.core.tasks.TaskHandler]
status: accepted
---
## Seam
- `@CallDeferred` - run this call in a Cloud Tasks request. Call-time extras:
  `_queue`, `_countdown`, `_eta`, `_name`, `_target_version`,
  `_call_deferred`.
- `@PeriodicTask(interval, cronName)` - called from `/_tasks/cron`.
- `@CallableTask` on a `CallableTaskBase` subclass - user-triggerable task with
  `canCall()`, `dataSkel()`, `execute()`.
- `@StartupTask`, and `@retry_n_times(n, email_recipients, tpl)` to bound
  retries.
- `QueryIter` subclass (`handleEntry`, `handleFinish`, `handleError`) for
  result sets too large for one request.
- `conf.tasks_custom_environment_handler` - a `CustomEnvironmentHandler`
  instance carrying extra request environment into the deferred request.

## Rules
- Arguments must be JSON-serializable; the payload is
  `(command, (funcPath, args, kwargs, env))`.
- `QueryIter`: all state goes into `customData` and must be JSON-serializable.
  Each chunk may run on a different instance, so class attributes are lost.
- Periodic task functions must not start with `_` (RuntimeError at import).
- Raise `PermanentTaskFailure` to stop retrying. Every other exception is
  converted into `errors.RequestTimeout` so the queue retries.
- Do not modify or subclass `TaskHandler` (its docstring says so).
- The queue named in `_queue` / `conf.tasks_default_queues` must exist in
  `queue.yaml`.

## Traps
- Without a `queueRegion` (local dev without `TASKS_EMULATOR`) tasks run
  inline: appended to `req.pendingTasks` and executed after the response - or
  immediately when there is no request (warmup). Behaviour differs from
  production.
- A deferred call always returns `None`. Never use its return value.
- Calling a `@CallDeferred` super method from a `@CallDeferred` override
  defers twice; pass `_call_deferred=False`.
- Deferring inside a transaction is handled for you: a transaction marker is
  stored, `_countdown` is raised to at least 90 seconds, and the task is
  dropped if the transaction never committed.
- The deferred request restores only a *partial* session (user data from the
  payload, `loaded` stays False - see the FIXME in `TaskHandler.deferred`).
  Session-dependent code can misbehave there.
- The session user dict travels inside the task payload; only `password` is
  stripped.
- `_countdown` and `_eta` together raise ValueError.
- The queue key is the task path: `<modulePath>/<name>` for bound methods,
  `<name>.<module>` for unbound functions. Renaming a module changes the queue
  mapping.
- `retry_n_times` reads `X-Appengine-Taskretrycount`; outside a task request
  the count is -1, so the retry budget is effectively never exhausted there.

## Why not
`TaskHandler` endpoints are `@exposed` without `@skey` on purpose: the queue
cannot present a security key. They are protected by `_validate_request`,
which checks the caller IP against `_appengineServiceIPs` and requires the
`X-AppEngine-TaskName` (and for cron `X-Appengine-Cron`) header. Do not add
your own unauthenticated endpoints modelled after this.

## See also
[skeleton](skeleton.md), [bones/relational](bones/relational.md),
[email](email.md), [cache](cache.md)
