import warnings
from viur.core.config import conf as core_conf


class DBConfig:
    """DEPRECATED"""
    """This class only exists for compatibility reasons and this file will be removed in the future"""
    _map = {
        "traceQueries": [core_conf.debug.trace_queries, "conf.debug.trace_queries"],
        "memcache_client": [core_conf.db.memcache_client, "conf.db.memcache_client"]
    }

    def __setitem__(self, key, value):
        if key in self._map:
            warnings.warn(
                f"db.conf is deprecated and will be removed. Please use {self._map[key][1]} instead",
                DeprecationWarning,
                stacklevel=3,
            )
            self._map[key][0] = value

    def __getitem__(self, key):
        if key in self._map:
            warnings.warn(
                f"db.conf is deprecated and will be removed. Please use {self._map[key][1]} instead",
                DeprecationWarning,
                stacklevel=3,
            )
            return self._map[key][0]


conf = DBConfig()
