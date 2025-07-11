import datetime

from google.appengine.ext.testbed import Testbed

import logging
import sys
import typing as t

from viur.core.config import conf
from .types import Entity, Key

MEMCACHE_MAX_BATCH_SIZE = 30
MEMCACHE_NAMESPACE = "viur-datastore"
MEMCACHE_TIMEOUT: int | datetime.timedelta = datetime.timedelta(days=1)
MEMCACHE_MAX_SIZE: t.Final[int] = 1_000_000
TESTBED = None
"""

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
    "get",
    "put",
    "delete",
    "flush",
]


def get(keys: t.Union[Key, list[Key]], namespace: t.Optional[str] = None) -> t.Union[Entity, list[Entity], None]:
    """
    Reads data form the memcache.
    :param keys: Unique identifier(s) for one or more entry(s).
    :param namespace: Optional namespace to use.
    :return: The entity (or None if it has not been found), or a list of entities.
    """
    if not check_for_memcache():
        return None

    namespace = namespace or MEMCACHE_NAMESPACE
    single_request = not isinstance(keys, (list, tuple, set))
    if single_request:
        keys = [keys]
    keys = [str(key) for key in keys]  # Enforce that all keys are strings
    cached_data = {}
    result = []
    try:
        while keys:
            cached_data |= conf.db.memcache_client.get_multi(keys[:MEMCACHE_MAX_BATCH_SIZE], namespace=namespace)
            keys = keys[MEMCACHE_MAX_BATCH_SIZE:]
    except Exception as e:
        logging.error(f"""Failed to get keys form the memcache with {e=}""")
    for key, value in cached_data.items():
        entity = Entity(Key(key))
        entity |= value
        result.append(entity)
    if single_request:
        return result[0] if result else None
    return result if result else None


def put(
    data: t.Union[Entity, t.Dict[Key, Entity], t.Iterable[Entity]],
    namespace: t.Optional[str] = None,
    timeout: t.Optional[t.Union[int, datetime.timedelta]] = None
) -> bool:
    """
    Writes Data to the memcache.
    :param data: Data to write
    :param namespace: Optional namespace to use.
    :param timeout: Optional timeout in seconds or a timedelta object.
    :return: A boolean indicating success.
    """
    if not check_for_memcache():
        return False

    namespace = namespace or MEMCACHE_NAMESPACE
    timeout = timeout or MEMCACHE_TIMEOUT
    if isinstance(timeout, datetime.timedelta):
        timeout = timeout.total_seconds()

    if isinstance(data, (list, tuple, set)):
        data = {item.key: item for item in data}
    elif isinstance(data, Entity):
        data = {data.key: data}
    elif not isinstance(data, dict):
        raise TypeError(f"Invalid type {type(data)}. Expected a db.Entity, list or dict.")
    # Add only values to cache <= MEMMAX_SIZE (1.000.000)
    data = {str(key): value for key, value in data.items() if get_size(value) <= MEMCACHE_MAX_SIZE}

    keys = list(data.keys())
    try:
        while keys:
            data_batch = {key: data[key] for key in keys[:MEMCACHE_MAX_BATCH_SIZE]}
            conf.db.memcache_client.set_multi(data_batch, namespace=namespace, time=timeout)
            keys = keys[MEMCACHE_MAX_BATCH_SIZE:]
        return True
    except Exception as e:
        logging.error(f"""Failed to put data to the memcache with {e=}""")
        return False


def delete(keys: t.Union[Key, list[Key]], namespace: t.Optional[str] = None) -> None:
    """
    Deletes an Entry form memcache.
    :param keys: Unique identifier(s) for one or more entry(s).
    :param namespace: Optional namespace to use.
    """
    if not check_for_memcache():
        return None

    namespace = namespace or MEMCACHE_NAMESPACE
    if not isinstance(keys, list):
        keys = [keys]
    keys = [str(key) for key in keys]  # Enforce that all keys are strings
    try:
        while keys:
            conf.db.memcache_client.delete_multi(keys[:MEMCACHE_MAX_BATCH_SIZE], namespace=namespace)
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
        logging.warning(f"""conf.db.memcache_client is 'None'. It can not be used.""")
        return False
    init_testbed()
    return True


def init_testbed() -> None:
    global TESTBED
    if TESTBED is None and conf.instance.is_dev_server and conf.db.memcache_client:
        TESTBED = Testbed()
        TESTBED.activate()
        TESTBED.init_memcache_stub()
