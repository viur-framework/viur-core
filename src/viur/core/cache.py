import logging, os
from datetime import timedelta
from functools import wraps
from hashlib import sha512
from typing import List, Union, Callable, Tuple, Dict

from viur.core import tasks, utils, db, current
from viur.core.config import conf

"""
    This module implements a cache that can be used to serve entire requests or cache the output of any function
    (as long it's result can be stored in datastore). The intended use is to wrap functions that can be called from
    the outside (@exposed) with the @enableCache decorator. This will enable the cache provided in this module for that
    function, intercepting all calls to this function and serve a cached response instead of calling the function if
    possible. Authenticated users with "root" access can always bypass this cache by sending the X-Viur-Disable-Cache
    http Header    along with their requests. Entities in this cache will expire if
        - Their TTL is exceeded
        - They're explicitly removed from the cache by calling :meth:`viur.core.cache.flushCache` using their path
        - A Datastore entity that has been accessed using db.Get() from within the cached function has been modified
        - The wrapped function has run a query over a kind in which an entity has been added/edited/deleted

    ..Warning: As this cache is intended to be used with exposed functions, it will not only store the result of the
        wrapped function, but will also store and restore the Content-Type http header. This can cause unexpected
        behaviour if it's used to cache the result of non top-level functions, as calls to these functions now may
        cause this header to be rewritten.
"""

viurCacheName = "viur-cache"


def keyFromArgs(f: Callable, userSensitive: int, languageSensitive: bool, evaluatedArgs: List[str], path: str,
                args: Tuple, kwargs: Dict) -> str:
    """
        Utility function to derive a unique but stable string-key that can be used in a datastore-key
        for the given wrapped function f, the parameter *args and **kwargs it has been called with,
        the path-components from the url that point to the outer @exposed function which handles this request
        as well as the configuration (userSensitive, languageSensitive and evaluatedArgs) provided to the @enableCache
        decorator. To derive the key, we'll first map all positional arguments to their keyword equivalent, construct
        a dict with the parameters having an effect on the result, merge the context variables (language, session state)
        in, sort this dict by key, cast it to string and return it's sha512 hash.

        :param f: Callable which is inspected for its signature
            (we need to figure out what positional arguments map to which key argument)
        :param userSensitive: Signals wherever the output of f depends on the current user.
            0 means independent of wherever the user is a guest or known, all will get the same content.
            1 means cache only for guests, no cache will be performed if the user is logged-in.
            2 means cache in two groups, one for guests and one for all users
            3 will cache the result of that function for each individual users separately.
        :param evaluatedArgs: List of keyword-arguments having influence to the output generated by
            that function. This list *must* complete! Parameters not named here are ignored!
        :param path: Path to the function called but without parameters (ie. "/page/view")
        :returns: The unique key derived
    """
    res = {}
    argsOrder = list(f.__code__.co_varnames)[1: f.__code__.co_argcount]
    # Map default values in
    reversedArgsOrder = argsOrder[:: -1]
    for defaultValue in list(f.__defaults__ or [])[:: -1]:
        res[reversedArgsOrder.pop(0)] = defaultValue
    del reversedArgsOrder
    # Map args in
    setArgs = []  # Store a list of args already set by *args
    for idx in range(0, min(len(args), len(argsOrder))):
        if argsOrder[idx] in evaluatedArgs:
            setArgs.append(argsOrder[idx])
            res[argsOrder[idx]] = args[idx]
    # Last, we map the kwargs in
    for k, v in kwargs.items():
        if k in evaluatedArgs:
            if k in setArgs:
                raise AssertionError("Got dupplicate arguments for %s" % k)
            res[k] = v
    if userSensitive:
        user = current.user.get()
        if userSensitive == 1 and user:  # We dont cache requests for each user separately
            return None
        elif userSensitive == 2:
            if user:
                res["__user"] = "__ISUSER"
            else:
                res["__user"] = None
        elif userSensitive == 3:
            if user:
                res["__user"] = user["key"]
            else:
                res["__user"] = None
    if languageSensitive:
        res["__lang"] = current.language.get()
    if conf["viur.cacheEnvironmentKey"]:
        try:
            res["_cacheEnvironment"] = conf["viur.cacheEnvironmentKey"]()
        except RuntimeError:
            return None
    res["__path"] = path  # Different path might have different output (html,xml,..)
    try:
        appVersion = os.getenv("GAE_VERSION")
    except:
        logging.error("Could not determine the current application version! Caching might produce unexpected results!")
        appVersion = ""
    res["__appVersion"] = appVersion
    # Last check, that every parameter is satisfied:
    if not all([x in res.keys() for x in argsOrder]):
        # we have too few parameters for this function; that wont work
        return None
    res = list(res.items())  # flatten our dict to a list
    res.sort(key=lambda x: x[0])  # sort by keys
    mysha512 = sha512()
    mysha512.update(str(res).encode("UTF8"))
    return mysha512.hexdigest()


def wrapCallable(f, urls: List[str], userSensitive: int, languageSensitive: bool,
                 evaluatedArgs: List[str], maxCacheTime: int):
    """
        Does the actual work of wrapping a callable.
        Use the decorator enableCache instead of calling this directly.
    """

    @wraps(f)
    def wrapF(self, *args, **kwargs) -> Union[str, bytes]:
        currReq = current.request.get()
        if conf["viur.disableCache"] or currReq.disableCache:
            # Caching disabled
            if conf["viur.disableCache"]:
                logging.debug("Caching is disabled by config")
            return f(self, *args, **kwargs)
        # How many arguments are part of the way to the function called (and how many are just *args)
        offset = -len(currReq.args) or len(currReq.path_list)
        path = "/" + "/".join(currReq.path_list[: offset])
        if not path in urls:
            # This path (possibly a sub-render) should not be cached
            logging.debug("Not caching for %s" % path)
            return f(self, *args, **kwargs)
        key = keyFromArgs(f, userSensitive, languageSensitive, evaluatedArgs, path, args, kwargs)
        if not key:
            # Something is wrong (possibly the parameter-count)
            # Let's call f, but we knew already that this will clash
            return f(self, *args, **kwargs)
        dbRes = db.Get(db.Key(viurCacheName, key))
        if dbRes is not None:
            if not maxCacheTime \
                or dbRes["creationtime"] > utils.utcNow() - timedelta(seconds=maxCacheTime):
                # We store it unlimited or the cache is fresh enough
                logging.debug("This request was served from cache.")
                currReq.response.headers['Content-Type'] = dbRes["content-type"]
                return dbRes["data"]
        # If we made it this far, the request wasn't cached or too old; we need to rebuild it
        oldAccessLog = db.startDataAccessLog()
        try:
            res = f(self, *args, **kwargs)
        finally:
            accessedEntries = db.endDataAccessLog(oldAccessLog)
        dbEntity = db.Entity(db.Key(viurCacheName, key))
        dbEntity["data"] = res
        dbEntity["creationtime"] = utils.utcNow()
        dbEntity["path"] = path
        dbEntity["content-type"] = currReq.response.headers['Content-Type']
        dbEntity["accessedEntries"] = list(accessedEntries)
        dbEntity.exclude_from_indexes = {"data", "content-type"}  # We can save 2 DB-Writs :)
        db.Put(dbEntity)
        logging.debug("This request was a cache-miss. Cache has been updated.")
        return res

    return wrapF


def enableCache(urls: List[str], userSensitive: int = 0, languageSensitive: bool = False,
                evaluatedArgs: Union[List[str], None] = None, maxCacheTime: Union[int, None] = None):
    """
        Decorator to wrap this cache around a function. In order for this to function correctly, you must provide
        additional information so ViUR can determine in which situations it's possible to re-use an already cached
        result and when to call the wrapped function instead.

        ..Warning: It's not possible to cache the result of a function relying on reading/modifying
            the environment (ie. setting custom http-headers). The only exception is the content-type header which
            will be stored along with the cached response.

        :param urls: A list of urls for this function, for which the cache should be enabled.
            A function can have several urls (eg. /page/view or /pdf/page/view), and it
            might should not be cached under all urls (eg. /admin/page/view).
        :param userSensitive: Signals wherever the output of f depends on the current user.
            0 means independent of wherever the user is a guest or known, all will get the same content.
            1 means cache only for guests, no cache will be performed if the user is logged-in.
            2 means cache in two groups, one for guests and one for all users
            3 will cache the result of that function for each individual users separately.
        :param languageSensitive: If true, signals that the output of f might got translated.
            If true, the result of that function is cached separately for each language.
        :param evaluatedArgs: List of keyword-arguments having influence to the output generated by
            that function. This list *must* be complete! Parameters not named here are ignored!
            Warning: Double-check this list! F.e. if that function generates a list of entries and
            you miss the parameter "order" here, it would be impossible to sort the list.
            It would always have the ordering it had when the cache-entry was created.
        :param maxCacheTime: Specifies the maximum time an entry stays in the cache in seconds.
            Note: Its not erased from the db after that time, but it won't be served anymore.
            If None, the cache stays valid forever (until manually erased by calling flushCache.
    """
    if evaluatedArgs is None:
        evaluatedArgs = []
    assert not any([x.startswith("_") for x in evaluatedArgs]), "A evaluated Parameter cannot start with an underscore!"
    return lambda f: wrapCallable(f, urls, userSensitive, languageSensitive, evaluatedArgs, maxCacheTime)


@tasks.CallDeferred
def flushCache(prefix: str = None, key: Union[db.Key, None] = None, kind: Union[str, None] = None):
    """
        Flushes the cache. Its possible the flush only a part of the cache by specifying
        the path-prefix. The path is equal to the url that caused it to be cached (eg /page/view) and must be one
        listed in the 'url' param of :meth:`viur.core.cache.enableCache`.

        :param prefix: Path or prefix that should be flushed.
        :param key: Flush all cache entries which may contain this key. Also flushes entries
            which executed a query over that kind.
        :param kind: Flush all cache entries which executed a query over that kind.

        Examples:
            - "/" would flush the main page (and only that),
            - "/*" everything from the cache, "/page/*" everything from the page-module (default render),
            - and "/page/view/*" only that specific subset of the page-module.
    """
    if prefix is None and key is None and kind is None:
        prefix = "/*"
    if prefix is not None:
        items = db.Query(viurCacheName).filter("path =", prefix.rstrip("*")).iter()
        for item in items:
            db.Delete(item)
        if prefix.endswith("*"):
            items = db.Query(viurCacheName) \
                .filter("path >", prefix.rstrip("*")) \
                .filter("path <", prefix.rstrip("*") + u"\ufffd") \
                .iter()
            for item in items:
                db.Delete(item)
        logging.debug("Flushing cache succeeded. Everything matching \"%s\" is gone." % prefix)
    if key is not None:
        items = db.Query(viurCacheName).filter("accessedEntries =", key).iter()
        for item in items:
            logging.info("Deleted cache entry %s", item["path"])
            db.Delete(item.key)
        if not isinstance(key, db.Key):
            key = db.Key.from_legacy_urlsafe(key)  # hopefully is a string
        items = db.Query(viurCacheName).filter("accessedEntries =", key.kind).iter()
        for item in items:
            logging.info("Deleted cache entry %s", item["path"])
            db.Delete(item.key)
    if kind is not None:
        items = db.Query(viurCacheName).filter("accessedEntries =", kind).iter()
        for item in items:
            logging.info("Deleted cache entry %s", item["path"])
            db.Delete(item.key)


__all__ = ["enableCache", "flushCache"]
