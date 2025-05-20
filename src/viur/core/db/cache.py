import logging
import sys
import time
import typing as t

from viur.core.config import conf
from .types import Entity, Key

MEMCACHE_MAX_BATCH_SIZE = 30
MEMCACHE_NAMESPACE = "viur-datastore"
MEMCACHE_TIMEOUT = 60 * 60
MEMCACHE_MAX_SIZE = 1_000_000

"""

    This Module controls the Interaction with the Memcache from Google
    To activate the cache copy this code in your main.py
    ..  code-block:: python
    # Example
    from viur.core import conf
    if not conf.instance.is_dev_server:
        from google.appengine.api.memcache import Client
        conf.db_memcache_client = Client()
    else:
        conf.db_memcache_client = db.cache.LocalMemcache()

"""

__all__ = [
    "MEMCACHE_MAX_BATCH_SIZE",
    "MEMCACHE_NAMESPACE",
    "MEMCACHE_TIMEOUT",
    "MEMCACHE_MAX_SIZE",
    "get",
    "put",
    "delete",
    "LocalMemcache",
]


def get(keys: t.Union[str, Key, t.List[str], t.List[Key]]) -> t.Dict[str, dict]:
    """
    Reads data form the memcache.
    :param keys: Unique identifier(s) for one or more entry(s).
    :return: A dict with the entry(s) that found in the memcache.
    """
    if not check_for_memcache():
        return {}
    if not isinstance(keys, list):
        keys = [keys]
    keys = [str(key) for key in keys]  # Enforce that all keys are strings
    res = {}
    try:
        while keys:
            res |= conf.db_memcache_client.get_multi(keys[:MEMCACHE_MAX_BATCH_SIZE], namespace=MEMCACHE_NAMESPACE)
            keys = keys[MEMCACHE_MAX_BATCH_SIZE:]
    except Exception as e:
        logging.error(f"""Failed to get keys form the memcache with {e=}""")
    return res


def put(data: t.Union[Entity, t.Dict[Key, Entity], t.List[Entity]]):
    """
    Writes Data to the memcache.

    :param data: Data to write
    """
    if not check_for_memcache():
        return
    if isinstance(data, list):
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
            conf.db_memcache_client.set_multi(data_batch, namespace=MEMCACHE_NAMESPACE, time=MEMCACHE_TIMEOUT)
            keys = keys[MEMCACHE_MAX_BATCH_SIZE:]
    except Exception as e:
        logging.error(f"""Failed to put data to the memcache with {e=}""")


def delete(keys: t.Union[str, Key, t.List[str], t.List[Key]]) -> None:
    """
    Deletes an Entry form memcache.

    :param keys: Unique identifier(s) for one or more entry(s).
    """
    if not check_for_memcache():
        return
    if not isinstance(keys, list):
        keys = [keys]
    keys = [str(key) for key in keys]  # Enforce that all keys are strings
    try:
        while keys:
            conf.db_memcache_client.delete_multi(keys[:MEMCACHE_MAX_BATCH_SIZE], namespace=MEMCACHE_NAMESPACE)
            keys = keys[MEMCACHE_MAX_BATCH_SIZE:]
    except Exception as e:
        logging.error(f"""Failed to delete keys form the memcache with {e=}""")


def flush():
    """
    Deletes everything in memcache.
    """
    if not check_for_memcache():
        return
    try:
        conf.db_memcache_client.flush_all()
    except Exception as e:
        logging.error(f"""Failed to flush the memcache with {e=}""")


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
    if conf.db_memcache_client is None:
        logging.warning(f"""conf.db_memcache_client is 'None'. It can not be used.""")
        return False
    return True


class LocalMemcache:
    def __init__(self):
        self._data = {}

    def get_multi(self, keys: t.List[str], namespace: str = MEMCACHE_NAMESPACE):
        self._data.setdefault(namespace, {})
        res = {}
        for key in keys:
            if (data := self._data[namespace].get(key)) is not None:
                if data["__lifetime__"]["last_seen"] + data["__lifetime__"]["timeout"] > time.time():
                    res[key] = data["__data__"]
                else:
                    self._data[namespace].pop(key)
        return res

    def set_multi(self, data: t.Dict[str, t.Any], namespace: str = MEMCACHE_NAMESPACE, time: int = MEMCACHE_TIMEOUT):
        self._data.setdefault(namespace, {})
        for key, value in data.items():
            self._data[namespace][key] = {}
            self._data[namespace][key]["__data__"] = value
            self._data[namespace][key]["__lifetime__"] = {"timeout": time, "last_seen": time.time()}

    def delete_multi(self, keys: t.List[str] = [], namespace: str = MEMCACHE_NAMESPACE):
        self._data.setdefault(namespace, {})
        for key in keys:
            if (data := self._data[namespace].get(key)) is not None:
                self._data[namespace].pop(key)

    def flush_all(self):
        self._data.clear()
