import datetime
import logging
import sys
import typing as t

from viur.core.config import conf

MEMCACHE_MAX_BATCH_SIZE = 30
MEMCACHE_NAMESPACE = "viur-datastore"
MEMCACHE_TIMEOUT: int | datetime.timedelta = datetime.timedelta(days=1)
MEMCACHE_MAX_SIZE: t.Final[int] = 1_000_000
TESTBED = None
"""Mutable module state without a lock: ``init_testbed()`` assigns it via ``global``
without any synchronization. That is deliberate — ``check_for_memcache()`` (and with
it ``init_testbed()``) only runs when ``conf.instance.is_dev_server`` **and** a
``memcache_client`` are set, so never in multi-threaded production. The worst race
two development server threads can have is a doubly activated ``Testbed``: no data
loss, no wrong results.

    This Module controls the Interaction with the Memcache from Google
    To activate the cache copy this code in your main.py
    ..  code-block:: python
    # Example
    from viur.core import conf
    from google.appengine.api.memcache import Client
    conf.db.memcache_client = Client()
"""

__all__ = [
    "MEMCACHE_MAX_BATCH_SIZE",
    "MEMCACHE_NAMESPACE",
    "MEMCACHE_TIMEOUT",
    "MEMCACHE_MAX_SIZE",
    "cache_key",
    "get",
    "put",
    "delete",
    "flush",
]

Document: t.TypeAlias = dict[str, t.Any]
"""A record as the driver returns it: a dict carrying an ``_id``."""


def cache_key(kind: str, _id: str) -> str:
    """The memcache key of a record: kind and id together, as an id is only addressable within its kind."""
    return f"{kind}/{_id}"


def get(kind: str, ids: str | t.Iterable[str]) -> list[Document]:
    """
    Read documents from the memcache.

    :param kind: The kind the documents were stored under.
    :param ids: A single ``_id`` or several of them.
    :return: The documents found, in arbitrary order. Always a list, even for a single id — a document is a
        dict itself, so callers never have to tell a single hit from a collection.
    """
    # Inside a transaction reads must go straight to the datastore, so the cache
    # cannot serve a (potentially stale) value. Lazy import to avoid a cycle.
    from .utils import is_in_transaction
    if is_in_transaction():
        return []

    if not check_for_memcache():
        return []

    id_list = list(ids) if isinstance(ids, (list, set, tuple)) else [ids]
    if not id_list:
        return []

    keys = [cache_key(kind, _id) for _id in id_list]
    cached_data_result = {}
    try:
        while keys:
            if cached_data := conf.db.memcache_client.get_multi(keys[:MEMCACHE_MAX_BATCH_SIZE],
                                                                namespace=MEMCACHE_NAMESPACE):
                cached_data_result |= cached_data
            keys = keys[MEMCACHE_MAX_BATCH_SIZE:]
    except Exception as e:
        logging.error(f"""Failed to get keys form the memcache with {e=}""")

    return list(cached_data_result.values())


def put(
    kind: str,
    docs: Document | list[Document],
    timeout: int | datetime.timedelta | None = None,
) -> bool:
    """
    Write documents into the memcache.

    :param kind: The kind the documents are stored under.
    :param docs: A single document or several of them.
    :param timeout: An optional timeout in seconds or as a ``timedelta``.
    :return: Whether the write succeeded.
    """
    # Inside a transaction the write is not committed yet; caching it now would
    # serve values that may be rolled back. Lazy import to avoid a cycle.
    from .utils import is_in_transaction
    if is_in_transaction():
        return False

    if not check_for_memcache():
        return False
    if not docs:
        return False
    timeout = timeout or MEMCACHE_TIMEOUT
    if isinstance(timeout, datetime.timedelta):
        timeout = timeout.total_seconds()

    doc_list = docs if isinstance(docs, list) else [docs]

    # Add only values to cache <= MEMMAX_SIZE (1.000.000)
    data = {cache_key(kind, doc["_id"]): doc for doc in doc_list if get_size(doc) <= MEMCACHE_MAX_SIZE}

    keys = list(data.keys())
    try:
        while keys:
            data_batch = {key: data[key] for key in keys[:MEMCACHE_MAX_BATCH_SIZE]}
            conf.db.memcache_client.set_multi(data_batch, namespace=MEMCACHE_NAMESPACE, time=timeout)
            keys = keys[MEMCACHE_MAX_BATCH_SIZE:]
        return True
    except Exception as e:
        logging.error(f"""Failed to put data to the memcache with {e=}""")
        return False


def delete(kind: str, ids: str | t.Iterable[str]) -> None:
    """
    Delete documents from the memcache.

    :param kind: The kind the documents were stored under.
    :param ids: A single ``_id`` or several of them.
    """
    # Unlike get()/put(), delete() deliberately does NOT check is_in_transaction(): dropping a cache entry is
    # always safe, even when the surrounding transaction aborts later on — at worst it costs one additional,
    # but correct, refetch (a cache miss).
    if not check_for_memcache():
        return None
    id_list = list(ids) if isinstance(ids, (list, set, tuple)) else [ids]
    if not id_list:
        return None
    keys = [cache_key(kind, _id) for _id in id_list]
    try:
        while keys:
            conf.db.memcache_client.delete_multi(keys[:MEMCACHE_MAX_BATCH_SIZE], namespace=MEMCACHE_NAMESPACE)
            keys = keys[MEMCACHE_MAX_BATCH_SIZE:]
    except Exception as e:
        logging.error(f"""Failed to delete keys form the memcache with {e=}""")


def flush() -> bool:
    """
    Deletes everything in memcache.
    :return: A boolean indicating success.
    """
    if not check_for_memcache():
        return False
    try:
        conf.db.memcache_client.flush_all()
    except Exception as e:
        logging.error(f"""Failed to flush the memcache with {e=}""")
        return False
    return True


def get_size(obj: t.Any) -> int:
    """
    Utility function that counts the size of an object in bytes.
    """
    if isinstance(obj, dict):
        return sum(get_size([k, v]) for k, v in obj.items())
    elif isinstance(obj, list):
        return sum(get_size(x) for x in obj)

    return sys.getsizeof(obj)


def check_for_memcache() -> bool:
    if conf.db.memcache_client is None:
        # logging.warning(f"""conf.db.memcache_client is 'None'. It can not be used.""")
        return False

    init_testbed()
    return True


def init_testbed() -> None:
    global TESTBED
    if TESTBED is None and conf.instance.is_dev_server and conf.db.memcache_client:
        from google.appengine.ext.testbed import Testbed
        TESTBED = Testbed()
        TESTBED.activate()
        TESTBED.init_memcache_stub()
