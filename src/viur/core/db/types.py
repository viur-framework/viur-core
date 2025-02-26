"""
The constants, global variables and container classes used in the datastore api
"""
from __future__ import annotations

import base64
import datetime
import enum
import google.auth
import google.auth
import typing as t

from contextvars import ContextVar
from dataclasses import dataclass
from google.cloud._helpers import _to_bytes, _ensure_tuple_or_list
from google.cloud.datastore import _app_engine_key_pb2, Key as Datastore_key, Entity as Datastore_entity

if t.TYPE_CHECKING:
    from viur.core.skeleton import SkeletonInstance

# The property name pointing to an entities key in a query
KEY_SPECIAL_PROPERTY = "__key__"
# List of types that can be used in a datastore query
DATASTORE_BASE_TYPES = t.Union[None, str, int, float, bool, datetime.datetime, datetime.date, datetime.time, 'Key']  #
# Pointer to the current transaction this thread may be currently in
currentTransaction = ContextVar("CurrentTransaction", default=None)
# If set to a set for the current thread/request, we'll log all entities / kinds accessed
currentDbAccessLog: ContextVar[Optional[Set[Union[Key, str]]]] = ContextVar("Database-Accesslog", default=None)
# The current projectID, which can't be imported from transport.pyx
_, projectID = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])


class SortOrder(enum.Enum):
    Ascending = 1  # Sort A->Z
    Descending = 2  # Sort Z->A
    InvertedAscending = 3  # Fetch Z->A, then flip the results (useful in pagination to go from a start cursor backwards)
    InvertedDescending = 4  # Fetch A->Z, then flip the results (useful in pagination)


class SkelListRef(list):
    """
        This class is used to hold multiple skeletons together with other, commonly used information.

        SkelLists are returned by Skel().all()...fetch()-constructs and provide additional information
        about the data base query, for fetching additional entries.

        :ivar cursor: Holds the cursor within a query.
        :vartype cursor: str
    """

    __slots__ = ["baseSkel", "getCursor", "get_orders", "customQueryInfo", "renderPreparation"]

    def __init__(self, baseSkel: t.Optional["SkeletonInstance"] = None):
        """
            :param baseSkel: The baseclass for all entries in this list
        """
        super(SkelListRef, self).__init__()
        self.baseSkel = baseSkel or {}
        self.getCursor = lambda: None
        self.get_orders = lambda: None
        self.renderPreparation = None
        self.customQueryInfo = {}


class Key(Datastore_key):
    """
        The python representation of one datastore key. Unlike the original implementation, we don't store a
        reference to the project the key lives in. This is always expected to be the current project as ViUR
        does not support accessing data in multiple projects.
    """

    def __init__(self, *args, project=None, **kwargs):
        if project is None:
            project = projectID

        super().__init__(*args, project=project, **kwargs)

    def __str__(self):
        return self.to_legacy_urlsafe().decode("ASCII")

    '''
    def __repr__(self):
        return "<viur.datastore.Key %s/%s, parent=%s>" % (self.kind, self.id_or_name, self.parent)

    def __hash__(self):
        return hash("%s.%s.%s" % (self.kind, self.id, self.name))

    def __eq__(self, other):
        return isinstance(other, Key) and self.kind == other.kind and self.id == other.id and self.name == other.name \
            and self.parent == other.parent

    @staticmethod
    def _parse_path(path_args):
        """Parses positional arguments into key path with kinds and IDs.

        :type path_args: tuple
        :param path_args: A tuple from positional arguments. Should be
                          alternating list of kinds (string) and ID/name
                          parts (int or string).

        :rtype: :class:`list` of :class:`dict`
        :returns: A list of key parts with kind and ID or name set.
        :raises: :class:`ValueError` if there are no ``path_args``, if one of
                 the kinds is not a string or if one of the IDs/names is not
                 a string or an integer.
        """
        if len(path_args) == 0:
            raise ValueError("Key path must not be empty.")

        kind_list = path_args[::2]
        id_or_name_list = path_args[1::2]
        # Dummy sentinel value to pad incomplete key to even length path.
        partial_ending = object()
        if len(path_args) % 2 == 1:
            id_or_name_list += (partial_ending,)

        result = []
        for kind, id_or_name in zip(kind_list, id_or_name_list):
            curr_key_part = {}
            if isinstance(kind, str):
                curr_key_part["kind"] = kind
            else:
                raise ValueError(kind, "Kind was not a string.")

            if isinstance(id_or_name, str):
                if (id_or_name.isdigit()): # !!! VIUR
                    curr_key_part["id"] = int(id_or_name)
                else:
                    curr_key_part["name"] = id_or_name

            elif isinstance(id_or_name, int):
                curr_key_part["id"] = id_or_name
            elif id_or_name is not partial_ending:
                raise ValueError(id_or_name, "ID/name was not a string or integer.")

            result.append(curr_key_part)
        return result

    @classmethod
    def from_legacy_urlsafe(cls, strKey: str) -> Key:
        """
            Parses the string representation generated by :meth:to_legacy_urlsafe into a new Key object
            :param strKey: The string key to parse
            :return: The new Key object constructed from the string key
        """
        urlsafe = strKey.encode("ASCII")
        padding = b"=" * (-len(urlsafe) % 4)
        urlsafe += padding
        raw_bytes = base64.urlsafe_b64decode(urlsafe)
        reference = _app_engine_key_pb2.Reference()
        reference.ParseFromString(raw_bytes)
        resultKey = None
        for elem in reference.path.element:
            resultKey = Key(elem.type, elem.id or elem.name, parent=resultKey)
        return resultKey
    '''


class Entity(Datastore_entity):
    """
        The python representation of one datastore entity. The values of this entity are stored inside this dictionary,
        while the meta-data (it's key, the list of properties excluded from indexing and our version) as property values.
    """

    def __init__(self, key: Optional[Key] = None, exclude_from_indexes: Optional[List[str]] = None):
        super(Entity, self).__init__(key, exclude_from_indexes or [])
        assert not key or isinstance(key, Key), "Key must be a Key-Object (or None for an embedded entity)"


@dataclass
class QueryDefinition:
    """
        A single Query that will be run against the datastore.
    """
    kind: Optional[str]  # The datastore kind to run the query on. Can be None for kindles queries.
    filters: Dict[str, DATASTORE_BASE_TYPES]  # A dictionary of constrains to apply to the query.
    orders: List[Tuple[str, SortOrder]]  # The list of fields to sort the results by.
    distinct: Union[None, List[str]] = None  # If set, a list of fields that we should return distinct values of
    limit: int = 30  # The maximum amount of entities that should be returned
    startCursor: Optional[str] = None  # If set, we'll only return entities that appear after this cursor in the index.
    endCursor: Optional[str] = None  # If set, we'll only return entities up to this cursor in the index.
    currentCursor: Optional[str] = None  # Will be set after this query has been run, pointing after the last entity returned
