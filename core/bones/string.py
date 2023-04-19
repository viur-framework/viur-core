"""
The "StringBone" class is a subclass of the "BaseBone" class and represents a data field that
contains text values. It overrides some of the base class methods to provide specific functionality
for text fields.
"""

import logging
from typing import Dict, List, Optional, Set

from viur.core import db, utils
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.utils import currentLanguage


class StringBone(BaseBone):
    """
    Initializes a new instance of the StringBone class.

    :param caseSensitive: A boolean value indicating whether the text values in this field are
        case-sensitive or not.
    :param maxLength: The maximum length of the text values in this field.
    :param kwargs: Additional keyword arguments to pass to the base class constructor.
    """

    def __init__(
        self,
        *,
        caseSensitive: bool = True,
        maxLength: int = 254,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.caseSensitive = caseSensitive
        self.maxLength = maxLength

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        """
        Serializes a single value of this data field for storage in the database.

        :param value: The value to serialize.
        :param skel: The skeleton instance that this data field belongs to.
        :param name: The name of this data field.
        :param parentIndexed: A boolean value indicating whether the parent object has an index on
            this data field or not.
        :return: The serialized value.
        """
        if not self.caseSensitive and parentIndexed:
            return {"val": value, "idx": value.lower() if isinstance(value, str) else None}
        return value

    def singleValueUnserialize(self, value):
        """
        Unserializes a single value of this data field from the database.

        :param value: The serialized value to unserialize.
        :return: The unserialized value.
        """
        if isinstance(value, dict) and "val" in value:
            return value["val"]
        elif value:
            return str(value)
        else:
            return ""

    def getEmptyValue(self):
        """
        Returns the empty value for this data field.

        :return: An empty string.
        """
        return ""

    def isEmpty(self, value):
        """
        Determines whether a value for this data field is empty or not.

        :param value: The value to check for emptiness.
        :return: A boolean value indicating whether the value is empty or not.
        """
        if not value:
            return True

        return not bool(str(value).strip())

    def singleValueFromClient(self, value, skel, name, origData):
        """
        Converts a value for this data field from a client-provided representation to an internal
        representation.

        :param value: The value to convert from the client-provided representation.
        :param skel: The skeleton instance that this data field belongs to.
        :param name: The name of this data field.
        :param origData: The original data of the skeleton instance.
        :return: A tuple containing the converted value and a list of any validation errors encountered.
        """
        value = utils.escapeString(value, self.maxLength)
        err = self.isInvalid(value)
        if not err:
            return utils.escapeString(value, self.maxLength), None
        return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

    def buildDBFilter(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: Dict,
        prefix: Optional[str] = None
    ) -> db.Query:
        """
        Builds and returns a database filter for this data field based on the provided raw filter data.

        :param name: The name of this data field.
        :param skel: The skeleton instance that this data field belongs to.
        :param dbFilter: The database filter to add query clauses to.
        :param rawFilter: A dictionary containing the raw filter data for this data field.
        :param prefix: An optional prefix to add to the query clause.
        :return: The database filter with the added query clauses.
        """
        if name not in rawFilter and not any(
            [(x.startswith(name + "$") or x.startswith(name + ".")) for x in rawFilter.keys()]
        ):
            return super().buildDBFilter(name, skel, dbFilter, rawFilter, prefix)

        if not self.languages:
            namefilter = name
        else:
            lang = None
            for key in rawFilter.keys():
                if key.startswith("%s." % name):
                    langStr = key.replace("%s." % name, "")
                    if langStr in self.languages:
                        lang = langStr
                        break
            if not lang:
                lang = currentLanguage.get()  # currentSession.getLanguage()
                if not lang or not lang in self.languages:
                    lang = self.languages[0]
            namefilter = "%s.%s" % (name, lang)

        if name + "$lk" in rawFilter:  # Do a prefix-match
            if not self.caseSensitive:
                dbFilter.filter((prefix or "") + namefilter + ".idx >=", str(rawFilter[name + "$lk"]).lower())
                dbFilter.filter((prefix or "") + namefilter + ".idx <",
                                str(rawFilter[name + "$lk"] + u"\ufffd").lower())
            else:
                dbFilter.filter((prefix or "") + namefilter + " >=", str(rawFilter[name + "$lk"]))
                dbFilter.filter((prefix or "") + namefilter + " <", str(rawFilter[name + "$lk"] + u"\ufffd"))

        if name + "$gt" in rawFilter:  # All entries after
            if not self.caseSensitive:
                dbFilter.filter((prefix or "") + namefilter + ".idx >", str(rawFilter[name + "$gt"]).lower())
            else:
                dbFilter.filter((prefix or "") + namefilter + " >", str(rawFilter[name + "$gt"]))

        if name + "$lt" in rawFilter:  # All entries before
            if not self.caseSensitive:
                dbFilter.filter((prefix or "") + namefilter + ".idx <", str(rawFilter[name + "$lt"]).lower())
            else:
                dbFilter.filter((prefix or "") + namefilter + " <", str(rawFilter[name + "$lt"]))

        if name in rawFilter:  # Normal, strict match
            if not self.caseSensitive:
                dbFilter.filter((prefix or "") + namefilter + ".idx", str(rawFilter[name]).lower())
            else:
                dbFilter.filter((prefix or "") + namefilter, str(rawFilter[name]))

        return dbFilter

    def buildDBSort(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: Dict
    ) -> Optional[db.Query]:
        """
        Build a DB sort based on the specified name and a raw filter.

        :param name: The name of the attribute to sort by.
        :param skel: A SkeletonInstance object.
        :param dbFilter: A Query object representing the current DB filter.
        :param rawFilter: A dictionary containing the raw filter.
        :return: The Query object with the specified sort applied.
        :rtype: Optional[google.cloud.ndb.query.Query]
        """
        if "orderby" in rawFilter and (rawFilter["orderby"] == name or (
            isinstance(rawFilter["orderby"], str) and rawFilter["orderby"].startswith(
                "%s." % name) and self.languages)):
            if self.languages:
                lang = None
                if rawFilter["orderby"].startswith("%s." % name):
                    lng = rawFilter["orderby"].replace("%s." % name, "")
                    if lng in self.languages:
                        lang = lng
                if lang is None:
                    lang = currentLanguage.get()  # currentSession.getLanguage()
                    if not lang or not lang in self.languages:
                        lang = self.languages[0]
                if self.caseSensitive:
                    prop = "%s.%s" % (name, lang)
                else:
                    prop = "%s.%s.idx" % (name, lang)
            else:
                if self.caseSensitive:
                    prop = name
                else:
                    prop = name + ".idx"
            if "orderdir" in rawFilter and rawFilter["orderdir"] == "1":
                order = (prop, db.SortOrder.Descending)
            elif "orderdir" in rawFilter and rawFilter["orderdir"] == "2":
                order = (prop, db.SortOrder.InvertedAscending)
            elif "orderdir" in rawFilter and rawFilter["orderdir"] == "3":
                order = (prop, db.SortOrder.InvertedDescending)
            else:
                order = (prop, db.SortOrder.Ascending)
            inEqFilter = [x for x in dbFilter.queries.filters.keys() if  # FIXME: This will break on multi queries
                          (">" in x[-3:] or "<" in x[-3:] or "!=" in x[-4:])]
            if inEqFilter:
                inEqFilter = inEqFilter[0][: inEqFilter[0].find(" ")]
                if inEqFilter != order[0]:
                    logging.warning("I fixed you query! Impossible ordering changed to %s, %s" % (inEqFilter, order[0]))
                    dbFilter.order(inEqFilter, order)
                else:
                    dbFilter.order(order)
            else:
                dbFilter.order(order)
        return dbFilter

    def getSearchTags(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> Set[str]:
        """
        Returns a set of lowercased words that represent searchable tags for the given bone.

        :param skel: The skeleton instance being searched.
        :param name: The name of the bone to generate tags for.

        :return: A set of lowercased words representing searchable tags.
        :rtype: set
        """
        result = set()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            for line in str(value).splitlines():  # TODO: Can a StringBone be multiline?
                for word in line.split(" "):
                    result.add(word.lower())
        return result

    def getUniquePropertyIndexValues(self, skel, name: str) -> List[str]:
        """
        Returns a list of unique index values for a given property name.

        :param skel: The skeleton instance.
        :param name: The name of the property.
        :return: A list of unique index values for the property.
        :rtype: List[str]
        :raises NotImplementedError: If the StringBone has languages and the implementation
            for this case is not yet defined.
        """
        if self.languages:
            # Not yet implemented as it's unclear if we should keep each language distinct or not
            raise NotImplementedError()

        return super().getUniquePropertyIndexValues(skel, name)
