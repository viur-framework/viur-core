from __future__ import annotations

import logging
import time
import typing as t

from deprecated.sphinx import deprecated
from google.cloud import datastore, exceptions

from .overrides import entity_from_protobuf, key_from_protobuf
from .types import Entity, Key, QueryDefinition, SortOrder, current_db_access_log
from viur.core.config import conf
from viur.core.errors import HTTPException

# patching our key and entity classes
datastore.helpers.key_from_protobuf = key_from_protobuf
datastore.helpers.entity_from_protobuf = entity_from_protobuf

__client__ = datastore.Client()


def allocate_ids(kind_name: str, num_ids: int = 1, retry=None, timeout=None) -> list[Key]:
    if type(kind_name) is not str:
        raise TypeError("kind_name must be a string")
    return __client__.allocate_ids(Key(kind_name), num_ids, retry, timeout)


@deprecated(version="3.8.0", reason="Use 'db.allocate_ids' instead")
def AllocateIDs(kind_name):
    """
    Allocates a new, free unique id for a given kind_name.
    """
    if isinstance(kind_name, Key):  # so ein Murks...
        kind_name = kind_name.kind

    return allocate_ids(kind_name)[0]


def get(keys: t.Union[Key, t.List[Key]]) -> t.Union[t.List[Entity], Entity, None]:
    """
    Retrieves an entity (or a list thereof) from datastore.
    If only a single key has been given we'll return the entity or none in case the key has not been found,
    otherwise a list of all entities that have been looked up (which may be empty)
    :param keys: A datastore key (or a list thereof) to lookup
    :return: The entity (or None if it has not been found), or a list of entities.
    """
    _write_to_access_log(keys)

    if isinstance(keys, (list, set, tuple)):
        res_list = list(__client__.get_multi(keys))
        res_list.sort(key=lambda k: keys.index(k.key) if k else -1)
        return res_list

    return __client__.get(keys)


@deprecated(version="3.8.0", reason="Use 'db.get' instead")
def Get(keys: t.Union[Key, t.List[Key]]) -> t.Union[t.List[Entity], Entity, None]:
    return get(keys)


def put(entities: t.Union[Entity, t.List[Entity]]):
    """
    Save an entity in the Cloud Datastore.
    Also ensures that no string-key with a digit-only name can be used.
    :param entities: The entities to be saved to the datastore.
    """
    _write_to_access_log(entities)
    if isinstance(entities, Entity):
        return __client__.put(entities)

    return __client__.put_multi(entities=entities)


@deprecated(version="3.8.0", reason="Use 'db.put' instead")
def Put(entities: t.Union[Entity, t.List[Entity]]) -> t.Union[Entity, None]:
    return put(entities)


def delete(keys: t.Union[Entity, t.List[Entity], Key, t.List[Key]]):
    """
    Deletes the entities with the given key(s) from the datastore.
    :param keys: A Key (or a t.List of Keys) to delete
    """

    _write_to_access_log(keys)
    if not isinstance(keys, (set, list, tuple)):
        return __client__.delete(keys)

    return __client__.delete_multi(keys)


@deprecated(version="3.8.0", reason="Use 'db.delete' instead")
def Delete(keys: t.Union[Entity, t.List[Entity], Key, t.List[Key]]):
    return delete(keys)


def run_in_transaction(func: t.Callable, *args, **kwargs) -> t.Any:
    """
    Runs the function given in :param:callee inside a transaction.
    Inside a transaction it's guaranteed that
    - either all or no changes are written to the datastore
    - no other transaction is currently reading/writing the entities accessed

    See (transactions)[https://cloud.google.com/datastore/docs/concepts/cloud-datastore-transactions] for more
    information.

    ..Warning: The datastore may produce unexpected results if an entity that have been written inside a transaction
        is read (or returned in a query) again. In this case you will the the *old* state of that entity. Keep that
        in mind if wrapping functions to run in a transaction that may have not been designed to handle this case.
    :param func: The function that will be run inside a transaction
    :param args: All args will be passed into the callee
    :param kwargs: All kwargs will be passed into the callee
    :return: Whatever the callee function returned
    :raises RuntimeError: If the maximum transaction retries exceeded
    """
    if __client__.current_transaction:
        res = func(*args, **kwargs)
    else:
        for i in range(3):
            try:
                with __client__.transaction():
                    res = func(*args, **kwargs)
                    break

            except HTTPException:
                raise
            except exceptions.Conflict:
                logging.error(f"Transaction failed with a conflict, trying again in {2 ** i} seconds")
                time.sleep(2 ** i)
                continue
            except Exception as e:
                logging.error(f"Transaction failed with exception, trying again in {2 ** i} seconds")
                logging.exception(e)
                time.sleep(2 ** i)
                continue
        else:
            raise RuntimeError(f"Maximum transaction retries exceeded")

    return res


@deprecated(version="3.8.0", reason="Use 'db.run_in_transaction' instead")
def RunInTransaction(callee: t.Callable, *args, **kwargs) -> t.Any:
    return run_in_transaction(callee, *args, **kwargs)


def count(kind: str = None, up_to=2 ** 31 - 1, queryDefinition: QueryDefinition = None) -> int:
    if not kind:
        kind = queryDefinition.kind

    query = __client__.query(kind=kind)
    if queryDefinition and queryDefinition.filters:
        for k, v in queryDefinition.filters.items():
            key, op = k.split(" ")
            if not isinstance(v, list):  # multi equal filters
                v = [v]
            for val in v:
                f = datastore.query.PropertyFilter(key, op, val)
                query.add_filter(filter=f)

    aggregation_query = __client__.aggregation_query(query)

    result = aggregation_query.count(alias="total").fetch(limit=up_to)
    return list(result)[0][0].value


@deprecated(version="3.8.0", reason="Use 'db.count' instead")
def Count(kind: str = None, up_to=2 ** 31 - 1, queryDefinition: QueryDefinition = None) -> int:
    return count(kind, up_to, queryDefinition)


def run_single_filter(query: QueryDefinition, limit: int) -> t.List[Entity]:
    """
        Internal helper function that runs a single query definition on the datastore and returns a list of
        entities found.
        :param query: The querydefinition (filters, orders, distinct etc.) to run against the datastore
        :param limit: How many results should at most be returned
        :return: The first *limit* entities that matches this query
    """

    qry = __client__.query(kind=query.kind)
    startCursor = None
    endCursor = None
    hasInvertedOrderings = None

    if query:
        if query.filters:
            for k, v in query.filters.items():
                key, op = k.split(" ")
                if not isinstance(v, list):  # multi equal filters
                    v = [v]
                for val in v:
                    f = datastore.query.PropertyFilter(key, op, val)
                    qry.add_filter(filter=f)

        if query.orders:
            hasInvertedOrderings = any(
                [
                    x[1] in [SortOrder.InvertedAscending, SortOrder.InvertedDescending]
                    for x in query.orders
                ]
            )
            qry.order = [
                x[0] if x[1] in [SortOrder.Ascending, SortOrder.InvertedDescending] else f"-{x[0]}"
                for x in query.orders
            ]

        if query.distinct:
            qry.distinct_on = query.distinct

        startCursor = query.startCursor
        endCursor = query.endCursor

    qryRes = qry.fetch(limit=limit, start_cursor=startCursor, end_cursor=endCursor)
    res = list(qryRes)

    query.currentCursor = qryRes.next_page_token
    if hasInvertedOrderings:
        res.reverse()
    return res


@deprecated(version="3.8.0", reason="Use 'run_single_filter' instead")
def runSingleFilter(query: QueryDefinition, limit: int) -> t.List[Entity]:
    run_single_filter(query, limit)


# helper function for access log
def _write_to_access_log(data: t.Union[Key, list[Key], Entity, list[Entity]]) -> None:
    if not conf.db.create_access_log:
        return
    access_log = current_db_access_log.get()
    if not isinstance(access_log, set):
        return  # access log not exist
    if not data:
        return
    if isinstance(data, Entity):
        access_log.add(data.key)
    elif isinstance(data, Key):
        access_log.add(data)
    else:
        for entry in data:
            if isinstance(entry, Entity):
                access_log.add(entry.key)
            elif isinstance(entry, Key):
                access_log.add(entry)


__all__ = [allocate_ids, delete, get, put, run_in_transaction, count]
