import datetime
import typing as t

from deprecated.sphinx import deprecated
from pymongo.client_session import ClientSession

from viur.core import current
from . import objectid
from .transport import get, put, run_in_transaction
from .types import current_db_access_log


def is_in_transaction() -> bool:
    """Is a transaction running right now (a nested one included)?"""
    # The import sits inside on purpose: the tests reload ``transport`` via ``importlib.reload``, which builds
    # a new ContextVar object, and a module level ``from`` import would keep the old one forever.
    from .transport import _current_session
    return _current_session.get() is not None


@deprecated(version="3.8.0", reason="Use 'db.utils.is_in_transaction' instead")
def IsInTransaction() -> bool:
    return is_in_transaction()


def get_or_insert(kind: str, _id: str, **defaults) -> dict:
    """
    Either creates a new document with the given ``kind``/``_id``, or returns the existing one.

    Its guaranteed that there is no race-condition here; it will never overwrite a
    previously created document. Extra keyword arguments passed to this function will be
    used to populate the document if it has to be created; otherwise they are ignored.

    :param kind: The kind the document lives in.
    :param _id: The ``_id`` which will be fetched or created.
    :returns: Returns the fetched or newly created document.
    """

    def txn(kind, _id, defaults):
        obj = get(kind, _id)
        if not obj:
            obj = {"_id": _id, **defaults}
            put(kind, obj)
        return obj

    if is_in_transaction():
        return txn(kind, _id, defaults)
    return run_in_transaction(txn, kind, _id, defaults)


@deprecated(version="3.8.0", reason="Use 'str(key)' instead")
@deprecated(version="3.9.0", reason="A key is already a string; there is nothing left to encode")
def encodeKey(key: str) -> str:
    """Return the key as a string — a no-op since keys became plain ``_id`` strings."""
    return str(key)


def acquire_transaction_success_marker() -> str:
    """
        Generates a token that will be written to the datastore (under "viur-transactionmarker") if the transaction
        completes successfully. Currently only used by deferredTasks to check if the task should actually execute
        or if the transaction it was created in failed.

        The marker id comes from ``objectid.new_id()`` rather than from the session: a ``ClientSession``
        carries no ``.id`` and its ``session_id`` is an undocumented driver internal this caller must not bind
        to, while all that is needed is an identifier unique to this transaction.

        :return: Name of the entry in viur-transactionmarker
    """
    from .transport import _current_session  # looked up per call, see is_in_transaction
    session: ClientSession | None = _current_session.get()
    assert session, "acquire_transaction_success_marker cannot be called outside an transaction"
    marker = objectid.new_id()
    request_data = current.request_data.get()
    if not request_data.get("__viur-transactionmarker__"):
        put("viur-transactionmarker", {
            "_id": marker,
            "creationdate": datetime.datetime.now(datetime.timezone.utc),
        })
        request_data["__viur-transactionmarker__"] = True
    return marker


def start_data_access_log() -> set[str]:
    """
        Clears our internal access log (which keeps track of which entries have been accessed in the current
        request). The old set of accessed entries is returned so that it can be restored with
        :func:`server.db.popAccessData` in case of nested caching. You must call popAccessData afterwards, otherwise
        we'll continue to log all entries accessed in subsequent request on the same thread!
        :return: t.Set of old accessed entries
    """
    old = current_db_access_log.get(set())
    current_db_access_log.set(set())
    return old


def startDataAccessLog() -> set[str]:
    return start_data_access_log()


def end_data_access_log(
    outer_access_log: set[str] | None = None,
) -> set[str] | None:
    """
       Retrieves the set of entries accessed so far.

       To clean up and restart the log, call :func:`viur.datastore.startAccessDataLog`.

       If you called :func:`server.db.startAccessDataLog` before, you can re-apply the old log using
       the outerAccessLog param. Otherwise, it will disable the access log.

       :param outerAccessLog: State of your log returned by :func:`server.db.startAccessDataLog`
       :return: t.Set of entries accessed
       """
    res = current_db_access_log.get()
    if isinstance(outer_access_log, set):
        current_db_access_log.set((outer_access_log or set()).union(res))
    else:
        current_db_access_log.set(None)
    return res


def endDataAccessLog(
    outerAccessLog: set[str] | None = None,
) -> set[str] | None:
    return end_data_access_log(outer_access_log=outerAccessLog)
