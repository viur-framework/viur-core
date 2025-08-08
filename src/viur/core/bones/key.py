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
    :param allowed_kinds: The allowed entity kinds for the KeyBone.
    :param check: Whether to check for entity existence.
    """
    type = "key"

    def __init__(
        self,
        *,
        descr: str = "Key",
        readOnly: bool = True,  # default is readonly
        visible: bool = False,  # default is invisible
        allowed_kinds: t.Optional[t.Iterable[str]] = None,  # None allows for any kind
        check: bool = False,  # check for entity existence
        **kwargs
    ):
        super().__init__(descr=descr, readOnly=readOnly, visible=visible, defaultValue=None, **kwargs)
        self.allowed_kinds = tuple(allowed_kinds) if allowed_kinds else None
        self.check = check

    def singleValueFromClient(self, value, skel=None, bone_name=None, client_data=None, parse_only: bool = False):
        # check for correct key
        if isinstance(value, str):
            value = value.strip()

        if self.allowed_kinds:
            try:
                key = db.key_helper(value, self.allowed_kinds[0], self.allowed_kinds[1:])
            except ValueError as e:
                return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, e.args[0])]
        else:
            try:
                key = db.normalize_key(value)
            except Exception as exc:
                logging.exception(f"Failed to normalize {value}: {exc}")
                return self.getEmptyValue(), [
                    ReadFromClientError(
                        ReadFromClientErrorSeverity.Invalid,
                        i18n.translate("core.bones.error.invalidkey", "No valid database key could be parsed")
                    )
                ]

        if not parse_only:
            # Check custom validity
            if err := self.isInvalid(key):
                return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

            if self.check:
                if db.get(key) is None:
                    return self.getEmptyValue(), [
                        ReadFromClientError(
                            ReadFromClientErrorSeverity.Invalid,
                            i18n.translate("core.bones.error.keynotfound", "The provided database key does not exist")
                        )
                    ]

        return key, None

    def singleValueUnserialize(self, val):
        if not val:
            rval = None
        elif isinstance(val, db.Key):
            rval = db.normalize_key(val)
        else:
            rval, err = self.singleValueFromClient(val, parse_only=True)
            if err:
                raise ValueError(err[0].errorMessage)

        return rval

    def unserialize(self, skel: 'SkeletonInstance', name: str) -> bool:
        if (
                name == "key"
                and isinstance(skel.dbEntity, db.Entity)
                and skel.dbEntity.key
                and not skel.dbEntity.key.is_partial
        ):
            skel.accessedValues[name] = skel.dbEntity.key
            return True
        return super().unserialize(skel, name)

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        if name not in skel.accessedValues:
            return False
        if name == "key":
            skel.dbEntity.key = skel.accessedValues["key"]
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

    def _atomic_dump(self, value):
        if not value:
            return None

        return str(value)
