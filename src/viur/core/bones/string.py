import datetime
import logging
import typing as t
import warnings
from numbers import Number

from viur.core import current, db, utils
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity

if t.TYPE_CHECKING:
    from ..skeleton import SkeletonInstance

DB_TYPE_INDEXED: t.TypeAlias = dict[t.Literal["val", "idx", "sort_idx"], str]


class StringBone(BaseBone):
    """
    The "StringBone" represents a data field that contains text values.
    """
    type = "str"

    def __init__(
        self,
        *,
        caseSensitive: bool = True,
        max_length: int | None = 254,
        min_length: int | None = None,
        natural_sorting: bool | t.Callable = False,
        **kwargs
    ):
        """
        Initializes a new StringBone.

        :param caseSensitive: When filtering for values in this bone, should it be case-sensitive?
        :param max_length: The maximum length allowed for values of this bone. Set to None for no limitation.
        :param min_length: The minimum length allowed for values of this bone. Set to None for no limitation.
        :param natural_sorting: Allows a more natural sorting
            than the default sorting on the plain values.
            This uses the .sort_idx property.
            `True` enables sorting according to DIN 5007 Variant 2.
            With passing a `callable`, a custom transformer method can be set
            that creates the value for the index property.
        :param kwargs: Inherited arguments from the BaseBone.
        """
        # fixme: Remove in viur-core >= 4
        if "maxLength" in kwargs:
            warnings.warn("maxLength parameter is deprecated, please use max_length",
                          DeprecationWarning, stacklevel=2)
            max_length = kwargs.pop("maxLength")
        super().__init__(**kwargs)
        if max_length is not None and max_length <= 0:
            raise ValueError("max_length must be a positive integer or None")
        if min_length is not None and min_length <= 0:
            raise ValueError("min_length must be a positive integer or None")
        if min_length is not None and max_length is not None:
            if min_length > max_length:
                raise ValueError("min_length can't be greater than max_length")
        self.caseSensitive = caseSensitive
        self.max_length = max_length
        self.min_length = min_length
        if callable(natural_sorting):
            self.natural_sorting = natural_sorting
        elif not isinstance(natural_sorting, bool):
            raise TypeError("natural_sorting must be a callable or boolean!")
        elif not natural_sorting:
            self.natural_sorting = None
        # else: keep self.natural_sorting as is

    def type_coerce_single_value(self, value: t.Any) -> str:
        """Convert a value to a string (if not already)

        Converts a value that is not a string into a string
        if a meaningful conversion is possible (simple data types only).
        """
        if isinstance(value, str):
            return value
        elif isinstance(value, Number):
            return str(value)
        elif isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
            return value.isoformat()
        elif isinstance(value, db.Key):
            return value.to_legacy_urlsafe().decode("ASCII")
        elif not value:  # None or any other falsy value
            return self.getEmptyValue()
        else:
            raise ValueError(
                f"Value {value} of type {type(value)} cannot be coerced for {type(self).__name__} {self.name}"
            )

    def singleValueSerialize(
        self,
        value: t.Any,
        skel: "SkeletonInstance",
        name: str,
        parentIndexed: bool,
    ) -> str | DB_TYPE_INDEXED:
        """
        Serializes a single value of this data field for storage in the database.

        :param value: The value to serialize.
            It should be a str value, if not it is forced with :meth:`type_coerce_single_value`.
        :param skel: The skeleton instance that this data field belongs to.
        :param name: The name of this data field.
        :param parentIndexed: A boolean value indicating whether the parent object has an index on
            this data field or not.
        :return: The serialized value.
        """
        value = self.type_coerce_single_value(value)
        if (not self.caseSensitive or self.natural_sorting) and parentIndexed:
            serialized: DB_TYPE_INDEXED = {"val": value}
            if not self.caseSensitive:
                serialized["idx"] = value.lower()
            if self.natural_sorting:
                serialized["sort_idx"] = self.natural_sorting(value)
            return serialized
        return value

    def singleValueUnserialize(self, value: str | DB_TYPE_INDEXED) -> str:
        """
        Unserializes a single value of this data field from the database.

        :param value: The serialized value to unserialize.
        :return: The unserialized value.
        """
        if isinstance(value, dict) and "val" in value:
            value = value["val"]  # Process with the raw value
        if value:
            return str(value)
        else:
            return self.getEmptyValue()

    def getEmptyValue(self) -> str:
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

    def isInvalid(self, value: t.Any) -> str | None:
        """
        Returns None if the value would be valid for
        this bone, an error-message otherwise.
        """
        if self.max_length is not None and len(value) > self.max_length:
            return "Maximum length exceeded"
        if self.min_length is not None and len(value) < self.min_length:
            return "Minimum length not reached"
        return None

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        """
        Returns None and the escaped value if the value would be valid for
        this bone, otherwise the empty value and an error-message.
        """

        if not (err := self.isInvalid(str(value))):
            return utils.string.escape(value, self.max_length), None

        return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

    def buildDBFilter(
        self,
        name: str,
        skel: "SkeletonInstance",
        dbFilter: db.Query,
        rawFilter: dict,
        prefix: t.Optional[str] = None
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
                if key.startswith(f"{name}."):
                    langStr = key.replace(f"{name}.", "")
                    if langStr in self.languages:
                        lang = langStr
                        break
            if not lang:
                lang = current.language.get()  # currentSession.getLanguage()
                if not lang or not lang in self.languages:
                    lang = self.languages[0]
            namefilter = f"{name}.{lang}"

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
        skel: "SkeletonInstance",
        dbFilter: db.Query,
        rawFilter: dict
    ) -> t.Optional[db.Query]:
        """
        Build a DB sort based on the specified name and a raw filter.

        :param name: The name of the attribute to sort by.
        :param skel: A SkeletonInstance object.
        :param dbFilter: A Query object representing the current DB filter.
        :param rawFilter: A dictionary containing the raw filter.
        :return: The Query object with the specified sort applied.
        """
        if ((orderby := rawFilter.get("orderby"))
            and (orderby == name
                 or (isinstance(orderby, str) and orderby.startswith(f"{name}.") and self.languages))):
            if self.languages:
                lang = None
                if orderby.startswith(f"{name}."):
                    lng = orderby.replace(f"{name}.", "")
                    if lng in self.languages:
                        lang = lng
                if lang is None:
                    lang = current.language.get()
                    if not lang or lang not in self.languages:
                        lang = self.languages[0]
                prop = f"{name}.{lang}"
            else:
                prop = name
            if self.natural_sorting:
                prop += ".sort_idx"
            elif not self.caseSensitive:
                prop += ".idx"

            # fixme: VIUR4 replace theses stupid numbers defining a sort-order by a meaningful keys
            sorting = {
                "1": db.SortOrder.Descending,
                "2": db.SortOrder.InvertedAscending,
                "3": db.SortOrder.InvertedDescending,
            }.get(rawFilter.get("orderdir"), db.SortOrder.Ascending)
            order = (prop, sorting)
            inEqFilter = [x for x in dbFilter.queries.filters.keys()  # FIXME: This will break on multi queries
                          if (">" in x[-3:] or "<" in x[-3:] or "!=" in x[-4:])]
            if inEqFilter:
                inEqFilter = inEqFilter[0][: inEqFilter[0].find(" ")]
                if inEqFilter != order[0]:
                    logging.warning(f"I fixed you query! Impossible ordering changed to {inEqFilter}, {order[0]}")
                    dbFilter.order(inEqFilter, order)
                else:
                    dbFilter.order(order)
            else:
                dbFilter.order(order)
        return dbFilter

    def natural_sorting(self, value: str | None) -> str | None:
        """Implements a default natural sorting transformer.

        The sorting is according to DIN 5007 Variant 2
        and sets ö and oe, etc. equal.
        """
        if value is None:
            return None
        assert isinstance(value, str)
        if not self.caseSensitive:
            value = value.lower()

        # DIN 5007 Variant 2
        return value.translate(str.maketrans({
            "ö": "oe",
            "Ö": "Oe",
            "ü": "ue",
            "Ü": "Ue",
            "ä": "ae",
            "Ä": "Ae",
            "ẞ": "SS",
        }))

    def getSearchTags(self, skel: "SkeletonInstance", name: str) -> set[str]:
        """
        Returns a set of lowercased words that represent searchable tags for the given bone.

        :param skel: The skeleton instance being searched.
        :param name: The name of the bone to generate tags for.

        :return: A set of lowercased words representing searchable tags.
        """
        result = set()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            for line in str(value).splitlines():  # TODO: Can a StringBone be multiline?
                for word in line.split(" "):
                    result.add(word.lower())
        return result

    def getUniquePropertyIndexValues(self, skel: "SkeletonInstance", name: str) -> list[str]:
        """
        Returns a list of unique index values for a given property name.

        :param skel: The skeleton instance.
        :param name: The name of the property.
        :return: A list of unique index values for the property.
        :raises NotImplementedError: If the StringBone has languages and the implementation
            for this case is not yet defined.
        """
        if self.languages:
            # Not yet implemented as it's unclear if we should keep each language distinct or not
            raise NotImplementedError()

        return super().getUniquePropertyIndexValues(skel, name)

    def refresh(self, skel: "SkeletonInstance", bone_name: str) -> None:
        super().refresh(skel, bone_name)

        # TODO: duplicate code, this is the same iteration logic as in NumericBone
        new_value = {}
        for _, lang, value in self.iter_bone_value(skel, bone_name):
            new_value.setdefault(lang, []).append(self.type_coerce_single_value(value))

        if not self.multiple:
            # take the first one
            new_value = {lang: values[0] for lang, values in new_value.items() if values}

        if self.languages:
            skel[bone_name] = new_value
        elif not self.languages:
            # just the value(s) with None language
            skel[bone_name] = new_value.get(None, [] if self.multiple else self.getEmptyValue())

    def structure(self) -> dict:
        ret = super().structure() | {
            "maxlength": self.max_length,
            "minlength": self.min_length
        }
        return ret
