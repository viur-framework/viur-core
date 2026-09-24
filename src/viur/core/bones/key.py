import copy
import logging
import typing as t
from viur.core import db, i18n
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity


class KeyBone(BaseBone):
    """
    The KeyBone is used for managing keys in the database. It provides various methods for validating,
    converting, and storing key values, as well as querying the database.
    Key management is crucial for maintaining relationships between entities in the database, and the
    KeyBone class helps ensure that keys are handled correctly and efficiently throughout the system.

    :param descr: The description of the KeyBone.
    :param readOnly: Whether the KeyBone is read-only.
    :param visible: Whether the KeyBone is visible.
    :param kind: The kind this key belongs to. Every :class:`viur.core.skeleton.Skeleton` carries
        its own "key" bone, whose kind is not yet known when the class body runs - left as ``None``,
        it is filled in from the owning skeleton's ``kindName`` once that is known (see
        :meth:`setSystemInitialized`). A bone that references a *foreign* skeleton's key sets
        ``kind`` explicitly instead.
    :param check: Whether to check for entity existence.
    """
    type = "key"

    def __init__(
        self,
        *,
        descr: str = "Key",
        readOnly: bool = True,  # default is readonly
        visible: bool = False,  # default is invisible
        kind: str | None = None,  # None is filled in from the owning skeleton, see setSystemInitialized
        check: bool = False,  # check for entity existence
        tags: str | t.Iterable[str] = "technical",
        **kwargs
    ):
        super().__init__(descr=descr, readOnly=readOnly, visible=visible, defaultValue=None, tags=tags, **kwargs)
        self.kind = kind
        self.check = check

    def setSystemInitialized(self) -> None:
        """Fill in a missing kind from the owning skeleton.

        ``BaseSkeleton`` adds a ``key`` bone to every skeleton whose kind is not known yet
        while the class body runs, unlike bones pointing at a *foreign* skeleton, which
        bring their ``kind`` along in the constructor.
        """
        super().setSystemInitialized()
        if self.kind is None:
            self.kind = self.skel_cls.kindName
        if self.check and not self.kind:
            # A polymorphic KeyBone (kind="" - the target kind depends on the subclass) cannot
            # check against the database: db.get("", ...) would only fail on request time with
            # pymongo.errors.InvalidName. Better to fail loudly at startup.
            raise ValueError(
                f"KeyBone {self.skel_cls.__name__}.{self.name}: check=True requires a kind; "
                'a polymorphic KeyBone (kind="") cannot check'
            )

    def singleValueFromClient(self, value, skel=None, bone_name=None, client_data=None):
        if isinstance(value, str):
            value = value.strip()

        # An _id is any non-empty str, not necessarily an ObjectId hex, so that business keys
        # (singletons, unique locks) are valid references as well. Validating an ObjectId is
        # up to the creating side (db.put without an _id), not to reading or referencing one.
        if not (isinstance(value, str) and value):
            return self.getEmptyValue(), [
                ReadFromClientError(
                    ReadFromClientErrorSeverity.Invalid,
                    i18n.translate("core.bones.error.invalidkey", "No valid database key could be parsed")
                )
            ]

        # Check custom validity
        if err := self.isInvalid(value):
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

        if self.check and db.get(self.kind, value) is None:
            return self.getEmptyValue(), [
                ReadFromClientError(
                    ReadFromClientErrorSeverity.Invalid,
                    i18n.translate("core.bones.error.keynotfound", "The provided database key does not exist")
                )
            ]

        return value, None

    def singleValueUnserialize(self, val):
        if not val:
            return None
        # Any non-empty str is accepted, see singleValueFromClient. This runs on the read
        # path, where a stricter gate would turn reading a business key into a ValueError
        # (and thus a HTTP 500) although no write had ever warned about it.
        if isinstance(val, str) and val:
            return val

        raise ValueError(f"{val!r} is not a valid database key")

    def unserialize(self, skel: 'SkeletonInstance', name: str) -> bool:
        if name == "key" and (key := skel.dbEntity.get("_id")):
            skel.accessedValues[name] = key
            return True
        return super().unserialize(skel, name)

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        if name == "key":
            if name not in skel.accessedValues:
                return False

            skel.dbEntity["_id"] = skel.accessedValues[name]
            return True

        return super().serialize(skel, name, parentIndexed=parentIndexed)

    def buildDBFilter(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: dict,
        prefix: t.Optional[str] = None
    ) -> db.Query:
        """
        This method parses the search filter specified by the client in their request and converts
        it into a format that can be understood by the datastore. It takes care of ignoring filters
        that do not target this bone and safely handles malformed data in the raw filter.

        :param name: The property name of this bone in the Skeleton (not the description).
        :param skel: The :class:viur.core.skeleton.SkeletonInstance this bone is a part of.
        :param dbFilter: The current :class:viur.core.db.Query instance the filters should be
            applied to.
        :param rawFilter: The dictionary of filters the client wants to have applied.
        :param prefix: An optional string to prepend to the filter key. Defaults to None.

        :return: The modified :class:viur.core.db.Query.

        The method takes the following steps:

        #. Decodes the provided key(s) from the raw filter.
        #. If the filter contains a list of keys, it iterates through the list, creating a new
            filter for each key and appending it to the list of queries.
        #. If the filter contains a single key, it applies the filter directly to the query.
        #. In case of any invalid key or other issues, it raises a RuntimeError.
        """

        def _decodeKey(key):
            # Any non-empty str is a valid _id, business keys included.
            if isinstance(key, str) and key:
                return key
            logging.warning(f"Could not decode key {key}")
            raise RuntimeError()

        if name in rawFilter:
            if isinstance(rawFilter[name], list):
                if isinstance(dbFilter.queries, list):
                    raise ValueError("In-Filter already used!")
                elif dbFilter.queries is None:
                    return dbFilter  # Query is already unsatisfiable
                oldFilter = dbFilter.queries
                dbFilter.queries = []
                for key in rawFilter[name]:
                    newFilter = copy.deepcopy(oldFilter)
                    try:
                        if name == "key":
                            newFilter.filters[f"{prefix or ''}{db.KEY_SPECIAL_PROPERTY} ="] = _decodeKey(key)
                        else:
                            newFilter.filters[f"{prefix or ''}{name} ="] = _decodeKey(key)
                    except:  # Invalid key or something
                        raise RuntimeError()
                    dbFilter.queries.append(newFilter)
            else:
                try:
                    if name == "key":
                        dbFilter.filter(f"""{prefix or ""}{db.KEY_SPECIAL_PROPERTY} =""", _decodeKey(rawFilter[name]))
                    else:
                        dbFilter.filter(f"""{prefix or ""}{name} =""", _decodeKey(rawFilter[name]))
                except:  # Invalid key or something
                    raise RuntimeError()
            return dbFilter

    def _atomic_dump(self, value):
        if not value:
            return None

        return str(value)
