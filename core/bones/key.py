from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core import db, utils
from typing import Dict, Optional, Union, List
import logging, copy


class KeyBone(BaseBone):
    type = "key"

    def __init__(
        self,
        *,
        descr: str = "Key",
        readOnly: bool = True,  # default is readonly
        visible: bool = False,  # default is invisible
        allowed_kinds: Union[None, List[str]] = None,  # None allows for any kind
        check: bool = False,  # check for entity existence
        **kwargs
    ):
        super().__init__(descr=descr, readOnly=readOnly, visible=visible, defaultValue=None, **kwargs)
        self.allowed_kinds = allowed_kinds
        self.check = check

    def singleValueFromClient(self, value, skel, name, origData):
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
                key = db.normalizeKey(db.Key.from_legacy_urlsafe(value))
            except:
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
            Inverse of serialize. Evaluates whats
            read from the datastore and populates
            this bone accordingly.
            :param name: The property-name this bone has in its Skeleton (not the description!)
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
            and not skel.dbEntity.key.is_partial
        ):
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
            Serializes this bone into something we
            can write into the datastore.

            :param name: The property-name this bone has in its Skeleton (not the description!)
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
          rawFilter: Dict,
          prefix: Optional[str] = None
    ) -> db.Query:
        """
            Parses the searchfilter a client specified in his Request into
            something understood by the datastore.
            This function must:

                * Ignore all filters not targeting this bone
                * Safely handle malformed data in rawFilter
                    (this parameter is directly controlled by the client)

            :param name: The property-name this bone has in its Skeleton (not the description!)
            :param skel: The :class:`viur.core.db.Query` this bone is part of
            :param dbFilter: The current :class:`viur.core.db.Query` instance the filters should be applied to
            :param rawFilter: The dictionary of filters the client wants to have applied
            :returns: The modified :class:`viur.core.db.Query`
        """

        def _decodeKey(key):
            if isinstance(key, db.Key):
                return key
            else:
                try:
                    return db.Key.from_legacy_urlsafe(key)
                except Exception as e:
                    logging.exception(e)
                    logging.warning("Could not decode key %s" % key)
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
                            newFilter.filters["%s%s =" % (prefix or "", db.KEY_SPECIAL_PROPERTY)] = _decodeKey(key)
                        else:
                            newFilter.filters["%s%s =" % (prefix or "", name)] = _decodeKey(key)
                    except:  # Invalid key or something
                        raise RuntimeError()
                    dbFilter.queries.append(newFilter)
            else:
                try:
                    if name == "key":
                        dbFilter.filter("%s%s =" % (prefix or "", db.KEY_SPECIAL_PROPERTY), _decodeKey(rawFilter[name]))
                    else:
                        dbFilter.filter("%s%s =" % (prefix or "", name), _decodeKey(rawFilter[name]))
                except:  # Invalid key or something
                    raise RuntimeError()
            return dbFilter
