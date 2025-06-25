import datetime
from deprecated.sphinx import deprecated
import typing as t
from .transport import get, put, run_in_transaction, __client__
from .types import Entity, Key, current_db_access_log
from google.cloud.datastore.transaction import Transaction
from viur.core import current


def fix_unindexable_properties(entry: Entity) -> Entity:
    """
        Recursively walk the given Entity and add all properties to the list of unindexed properties if they contain
        a string longer than 1500 bytes (which is maximum size of a string that can be indexed). The datastore would
        return an error otherwise.
        https://cloud.google.com/datastore/docs/concepts/limits?hl=en#limits
    :param entry: The entity to fix (inplace)
    :return: The fixed entity
    """

    def has_unindexable_property(prop):
        if isinstance(prop, dict):
            return any([has_unindexable_property(x) for x in prop.values()])
        elif isinstance(prop, list):
            return any([has_unindexable_property(x) for x in prop])
        elif isinstance(prop, (str, bytes)):
            return len(prop) >= 1500
        else:
            return False

    unindexable_properties = set()
    for key, value in entry.items():
        if not has_unindexable_property(value):
            continue
        if isinstance(value, dict):
            inner_entity = Entity()
            inner_entity.update(value)
            entry[key] = fix_unindexable_properties(inner_entity)
            if isinstance(value, Entity):
                inner_entity.key = value.key
        else:
            unindexable_properties.add(key)
    entry.exclude_from_indexes = unindexable_properties
    return entry


def normalize_key(key: t.Union[None, Key, str]) -> t.Union[None, Key]:
    """
        Normalizes a datastore key (replacing _application with the current one)

        :param key: Key to be normalized.
        :return: Normalized key in string representation.
        """
    if key is None:
        return None
    if isinstance(key, str):
        key = Key.from_legacy_urlsafe(key)
    if key.parent:
        parent = normalize_key(key.parent)
    else:
        parent = None
    return Key(key.kind, key.id_or_name, parent=parent)


@deprecated(version="3.8.0", reason="Use 'db.normalize_key' instead")
def normalizeKey(key: t.Union[None, Key]) -> t.Union[None, Key]:
    return normalize_key(key)


def key_helper(
    in_key: t.Union[Key, str, int],
    target_kind: str,
    additional_allowed_kinds: t.Union[t.List[str], t.Tuple[str]] = (),
    adjust_kind: bool = False,
) -> Key:
    if isinstance(in_key, Key):
        if in_key.kind != target_kind and in_key.kind not in additional_allowed_kinds:
            if not adjust_kind:
                raise ValueError(
                    f"Kind mismatch: {in_key.kind!r} != {target_kind!r} (or in {additional_allowed_kinds!r})")
            in_key = Key(target_kind, in_key.id_or_name, parent=in_key.parent)
        return in_key
    elif isinstance(in_key, str):
        # Try to parse key from str
        try:
            decoded_key = normalize_key(in_key)
        except Exception as e:
            print(f"Failed to decode key: {in_key!r} {e}")
            decoded_key = None

        # If it did decode, recall keyHelper with Key object
        if decoded_key:
            return key_helper(
                decoded_key,
                target_kind=target_kind,
                additional_allowed_kinds=additional_allowed_kinds,
                adjust_kind=adjust_kind
            )

        # otherwise, construct key from str or int
        if in_key.isdigit():
            in_key = int(in_key)

        return Key(target_kind, in_key)
    elif isinstance(in_key, int):
        return Key(target_kind, in_key)

    raise NotImplementedError(f"Unsupported key type {type(in_key)}")


def keyHelper(
    inKey: t.Union[Key, str, int],
    targetKind: str,
    additionalAllowedKinds: t.Union[t.List[str], t.Tuple[str]] = (),
    adjust_kind: bool = False,
) -> Key:
    return key_helper(
        in_key=inKey,
        target_kind=targetKind,
        additional_allowed_kinds=additionalAllowedKinds,
        adjust_kind=adjust_kind
    )


def is_in_transaction() -> bool:
    return __client__.current_transaction is not None


@deprecated(version="3.8.0", reason="Use 'db.utils.is_in_transaction' instead")
def IsInTransaction() -> bool:
    return is_in_transaction()


def get_or_insert(key: Key, **kwargs) -> Entity:
    """
    Either creates a new entity with the given key, or returns the existing one.

    Its guaranteed that there is no race-condition here; it will never overwrite a
    previously created entity. Extra keyword arguments passed to this function will be
    used to populate the entity if it has to be created; otherwise they are ignored.

    :param key: The key which will be fetched or created.
    :returns: Returns the fetched or newly created Entity.
    """

    def txn(key, kwargs):
        obj = get(key)
        if not obj:
            obj = Entity(key)
            for k, v in kwargs.items():
                obj[k] = v
            put(obj)
        return obj

    if is_in_transaction():
        return txn(key, kwargs)
    return run_in_transaction(txn, key, kwargs)


@deprecated(version="3.8.0", reason="Use 'db.get_or_insert' instead")
def GetOrInsert(key: Key, **kwargs: t.Any) -> Entity:
    return get_or_insert(key, **kwargs)


@deprecated(version="3.8.0", reason="Use 'str(key)' instead")
def encodeKey(key: Key) -> str:
    """
        Return the given key encoded as string (mimicking the old str() behaviour of keys)
    """
    return str(key)


def acquire_transaction_success_marker() -> str:
    """
        Generates a token that will be written to the datastore (under "viur-transactionmarker") if the transaction
        completes successfully. Currently only used by deferredTasks to check if the task should actually execute
        or if the transaction it was created in failed.
        :return: Name of the entry in viur-transactionmarker
    """
    txn: Transaction | None = __client__.current_transaction
    assert txn, "acquire_transaction_success_marker cannot be called outside an transaction"
    marker = str(txn.id)
    request_data = current.request_data.get()
    if not request_data.get("__viur-transactionmarker__"):
        db_obj = Entity(Key("viur-transactionmarker", marker))
        db_obj["creationdate"] = datetime.datetime.now(datetime.timezone.utc)
        put(db_obj)
        request_data["__viur-transactionmarker__"] = True
    return marker


def start_data_access_log() -> t.Set[t.Union[Key, str]]:
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


def startDataAccessLog() -> t.Set[t.Union[Key, str]]:
    return start_data_access_log()


def end_data_access_log(
    outer_access_log: t.Optional[t.Set[t.Union[Key, str]]] = None,
) -> t.Optional[t.Set[t.Union[Key, str]]]:
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
    outerAccessLog: t.Optional[t.Set[t.Union[Key, str]]] = None,
) -> t.Optional[t.Set[t.Union[Key, str]]]:
    return end_data_access_log(outer_access_log=outerAccessLog)
