"""Tests for the dispatching in :mod:`viur.core.tasks`."""
from unittest import mock

from abstract import ViURTestCase


class TestCallDeferredDirectCall(ViURTestCase):
    """``_call_deferred=False`` must run the wrapped function right away.

    Whether a task queue can be reached is a property of the environment and must not
    change that: callers use the parameter precisely because they need the result now,
    for instance to invoke a `@CallDeferred` decorated super method.
    """

    def _decorated_task(self) -> tuple:
        """Build a freshly decorated task recording its calls.

        :return: Tuple of the tasks module, the decorated function and the list of calls.
        """
        from viur.core import tasks

        calls = []

        @tasks.CallDeferred
        def record_call(value):
            calls.append(value)

        self.addCleanup(tasks._deferred_tasks.pop, f"record_call.{__name__}", None)
        return tasks, record_call, calls

    def test_direct_call_without_queue(self):
        tasks, record_call, calls = self._decorated_task()
        with mock.patch.object(tasks, "queueRegion", None):
            record_call("a", _call_deferred=False)
        self.assertEqual(["a"], calls)

    def test_direct_call_without_queue_but_inside_a_request(self):
        """A request in the context must not turn the direct call into a pending task."""
        from viur.core import current

        tasks, record_call, calls = self._decorated_task()
        request = mock.MagicMock()
        request.request.headers = {}
        token = current.request.set(request)
        self.addCleanup(current.request.reset, token)

        with mock.patch.object(tasks, "queueRegion", None):
            record_call("b", _call_deferred=False)

        self.assertEqual(["b"], calls)
        request.pendingTasks.append.assert_not_called()


class TestRetryNTimesNotification(ViURTestCase):
    """The "task failed permanently" mail must actually be sent.

    :func:`viur.core.email.send_email` accepts ``tpl`` xor ``stringTemplate``. Passing
    both raises a ValueError which the surrounding ``except Exception`` swallows, so the
    notification was lost in exactly the situation it exists for.
    """

    def _run_failing_task(self, **decorator_kwargs) -> mock.Mock:
        """Run a task that always fails until the retry limit is reached.

        :return: The mock that replaced ``email.send_email``.
        """
        from viur.core import current, tasks
        from viur.core import email

        request = mock.MagicMock()
        request.request.headers = {"X-Appengine-Taskretrycount": "3"}
        token = current.request.set(request)
        self.addCleanup(current.request.reset, token)

        @tasks.retry_n_times(retries=3, email_recipients="admin@example.com", **decorator_kwargs)
        def always_fails():
            raise ValueError("boom")

        with mock.patch.object(email, "send_email") as send_email:
            with self.assertRaises(tasks.PermanentTaskFailure):
                always_fails()

        return send_email

    def test_default_template_is_passed_as_string_template(self):
        send_email = self._run_failing_task()
        send_email.assert_called_once()
        kwargs = send_email.call_args.kwargs
        self.assertNotIn("tpl", kwargs)
        self.assertIn("{{func_name}}", kwargs["stringTemplate"])

    def test_custom_template_is_passed_alone(self):
        send_email = self._run_failing_task(tpl="task_failed")
        send_email.assert_called_once()
        kwargs = send_email.call_args.kwargs
        self.assertEqual("task_failed", kwargs["tpl"])
        self.assertNotIn("stringTemplate", kwargs)

    def test_notification_reports_the_task(self):
        send_email = self._run_failing_task()
        kwargs = send_email.call_args.kwargs
        self.assertEqual("admin@example.com", kwargs["dests"])
        self.assertEqual("always_fails", kwargs["func_name"])
        self.assertEqual(3, kwargs["retries"])
