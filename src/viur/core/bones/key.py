import copy
import logging
import typing as t

from viur.core import db, utils
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity


class KeyBone(BaseBone):
    """
    The KeyBone is used for managing keys in the database. It provides various methods for validating,
    converting, and storing key values, as well as querying the database.
    Key management is crucial for maintaining relationships between entities in the database, and the
    KeyBone class helps ensure that keys are handled correctly and efficiently throughout the system.

    :param str descr: The description of the KeyBone.
    :param bool readOnly: Whether the KeyBone is read-only.
    :param bool visible: Whether the KeyBone is visible.
    :param Union[None, List[str]] allowed_kinds: The allowed entity kinds for the KeyBone.
    :param bool check: Whether to check for entity existence.
    """
    type = "key"

    def __init__(
        self,
        *,
        descr: str = "Key",
        readOnly: bool = True,  # default is readonly
        visible: bool = False,  # default is invisible
        allowed_kinds: None | list[str] = None,  # None allows for any kind
        check: bool = False,  # check for entity existence
        **kwargs
    ):
        super().__init__(descr=descr, readOnly=readOnly, visible=visible, defaultValue=None, **kwargs)
        self.allowed_kinds = allowed_kinds
        self.check = check

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        # check for correct key
        if isinstance(value, str):
            value = value.strip()

        if self.allowed_kinds:
            try:
                key = db.keyHelper(value, self.allowed_kinds[0], self.allowed_kinds[1:])
            except ValueError as e:
                return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, e.args[0])]
        else:
            try:
                if isinstance(value, db.Key):
                    key = db.normalizeKey(value)
                else:
                    key = db.normalizeKey(db.Key.from_legacy_urlsafe(value))
            except Exception as exc:
                logging.exception(f"Failed to normalize {value}: {exc}")
                return self.getEmptyValue(), [
                    ReadFromClientError(
                        ReadFromClientErrorSeverity.Invalid,
                        "The provided key is not a valid database key"
                    )
                ]

        # Check custom validity
        err = self.isInvalid(key)
        if err:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

        if self.check:
            if db.Get(key) is None:
                return self.getEmptyValue(), [
                    ReadFromClientError(
                        ReadFromClientErrorSeverity.Invalid,
                        "The provided key does not exist"
                    )
                ]

        return key, None

    def unserialize(self, skel: 'viur.core.skeleton.SkeletonValues', name: str) -> bool:
        """
        This method is the inverse of :meth:serialize. It reads the key value from the datastore
        and populates the corresponding KeyBone in the Skeleton. The method converts the value from
        the datastore into an appropriate format for further use in the program.

        :param skel: The SkeletonValues instance this bone is a part of.
        :param name: The property name of this bone in the Skeleton (not the description).

        :return: A boolean value indicating whether the operation was successful. Returns True if
            the key value was successfully unserialized and added to the accessedValues of the
            Skeleton, and False otherwise.

        .. note:: The method contains an inner function, fixVals(val), which normalizes and
            validates the key values before populating the bone.
        """

        def fixVals(val):
            if isinstance(val, str):
                try:
                    val = utils.normalizeKey(db.Key.from_legacy_urlsafe(val))
                except:
                    val = None
            elif not isinstance(val, db.Key):
                val = None
            return val

        if (name == "key"
            and isinstance(skel.dbEntity, db.Entity)
            and skel.dbEntity.key
                and not skel.dbEntity.key.is_partial):
            skel.accessedValues[name] = skel.dbEntity.key
            return True
        elif name in skel.dbEntity:
            val = skel.dbEntity[name]
            if isinstance(val, list):
                val = [fixVals(x) for x in val if fixVals(x)]
            else:
                val = fixVals(val)
            if self.multiple and not isinstance(val, list):
                if val:
                    val = [val]
                else:
                    val = []
            elif not self.multiple and isinstance(val, list):
                val = val[0]
            skel.accessedValues[name] = val
            return True
        return False

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        """
        This method serializes the KeyBone into a format that can be written to the datastore. It
        converts the key value from the Skeleton object into a format suitable for storage in the
        datastore.

        :param skel: The SkeletonInstance this bone is a part of.
        :param name: The property name of this bone in the Skeleton (not the description).
        :param parentIndexed: A boolean value indicating whether the parent entity is indexed or not.

        :return: A boolean value indicating whether the operation was successful. Returns True if
            the key value was successfully serialized and added to the datastore entity, and False
            otherwise.

        .. note:: Key values are always indexed, so the method discards any exclusion from indexing
            for key values.
        """
        if name in skel.accessedValues:
            if name == "key":
                skel.dbEntity.key = skel.accessedValues["key"]
            else:
                skel.dbEntity[name] = skel.accessedValues[name]
                skel.dbEntity.exclude_from_indexes.discard(name)  # Keys can never be not indexed
            return True
        return False

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
            if isinstance(key, db.Key):
                return key
            else:
                try:
                    return db.Key.from_legacy_urlsafe(key)
                except Exception as e:
                    logging.exception(e)
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
