from __future__ import annotations
from deprecated.sphinx import deprecated
from .overrides import key_from_protobuf, entity_from_protobuf
from .types import Key, Entity, QueryDefinition, SortOrder, currentDbAccessLog
from google.cloud import datastore
import binascii
import datetime
import typing as t

# patching our key and entity classes
datastore.helpers.key_from_protobuf = key_from_protobuf
datastore.helpers.entity_from_protobuf = entity_from_protobuf

__client__ = datastore.Client()

# Proxied Function / Classed
Get = __client__.get
Delete = __client__.delete


def allocate_ids(kind_name: str, num_ids: int = 1, retry=None, timeout=None) -> list[Key]:
    if type(kind_name) is not str:
        raise TypeError("kind_name must be a string")
    return __client__.allocate_ids(Key(kind_name), num_ids, retry, timeout)

@deprecated(version="3.8.0", reason="Use allocate_ids instead", action="always")
def AllocateIDs(kind_name):
    """
    Allocates a new, free unique id for a given kind_name.
    """
    if isinstance(kind_name, Key):  # so ein Murks...
        kind_name = kind_name.kind

    return allocate_ids(kind_name)[0]


def Get(keys: t.Union[Key, t.List[Key]]) -> t.Union[t.List[Entity], Entity, None]:
    """
        Retrieves an entity (or a list thereof) from datastore.
        If only a single key has been given we'll return the entity or none in case the key has not been found,
        otherwise a list of all entities that have been looked up (which may be empty)
        :param keys: A datastore key (or a list thereof) to lookup
        :return: The entity (or None if it has not been found), or a list of entities.
    """
    # accessLog = currentDbAccessLog.get()

    if isinstance(keys, list):
        # if isinstance(accessLog, set):
        #     accessLog.update(set(keys))

        resList = list(__client__.get_multi(keys))
        resList.sort(key=lambda x: keys.index(x.key) if x else -1)
        return resList

    # if isinstance(accessLog, set):
    #     accessLog.add(keys)

    return __client__.get(keys)


def Put(entities: t.Union[Entity, t.List[Entity]]):
    """
        Save an entity in the Cloud Datastore.
        Also ensures that no string-key with an digit-only name can be used.
        :param entity: The entity to be saved to the datastore.
    """
    if isinstance(entities, Entity):
        entities = entities,

    # accessLog = currentDbAccessLog.get()
    # if isinstance(accessLog, set):
    #     accessLog.update(set(i.key for i in entities if not i.key.is_partial))

    return __client__.put_multi(entities=entities)


def Delete(keys: t.Union[Entity, t.List[Entity], Key, t.List[Key]]):
    """
        Deletes the entities with the given key(s) from the datastore.
        :param keys: A Key (or a t.List of Keys) to delete
    """
    # accessLog = currentDbAccessLog.get()
    if isinstance(keys, list):
        # if isinstance(accessLog, set):
        #    accessLog.update(set(keys))
        return __client__.delete_multi(keys)

    # if isinstance(accessLog, set):
    #     accessLog.remove(keys)

    return __client__.delete(keys)


def IsInTransaction() -> bool:
    return __client__.current_transaction is not None


def RunInTransaction(callee: t.Callable, *args, **kwargs) -> t.Any:
    """
        Runs the function given in :param:callee inside a transaction.
        Inside a transaction it's guaranteed that
        - either all or no changes are written to the datastore
        - no other transaction is currently reading/writing the entities accessed

        See (transactions)[https://cloud.google.com/datastore/docs/concepts/cloud-datastore-transactions] for more
        information.

        ..Warning: The datastore may produce unexpected results if a entity that have been written inside a transaction
            is read (or returned in a query) again. In this case you will the the *old* state of that entity. Keep that
            in mind if wrapping functions to run in a transaction that may have not been designed to handle this case.
        :param callee: The function that will be run inside a transaction
        :param args: All args will be passed into the callee
        :param kwargs: All kwargs will be passed into the callee
        :return: Whatever the callee function returned
    """
    with __client__.transaction():
        res = callee(*args, **kwargs)
    return res


def Count(kind: str = None, up_to=2 ** 31 - 1, queryDefinition: QueryDefinition = None) -> t.Union[Key, t.List[Key]]:
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


def runSingleFilter(query: QueryDefinition, limit: int) -> t.List[Entity]:
    """
        Internal helper function that runs a single query definition on the datastore and returns a list of
        entities found.
        :param query: The querydefinition (filters, orders, distinct etc) to run against the datastore
        :param limit: How many results shoult at most be returned
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
                x[0] if x[1] in [SortOrder.Ascending, SortOrder.InvertedDescending] else "-" + x[0]
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


__all__ = [AllocateIDs, Delete, Get, Put, RunInTransaction, Count]
