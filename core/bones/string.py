import logging
from typing import Dict, List, Optional, Set

from viur.core import current, db, utils
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity


class StringBone(BaseBone):
    type = "str"

    def __init__(
        self,
        *,
        caseSensitive: bool = True,
        maxLength: int | None = 254,
        **kwargs
    ):
        """
        Initializes a new StringBone.

        :param caseSensitive: When filtering for values in this bone, should it be case-sensitive?
        :param maxLength: The maximum length allowed for values of this bone. Set to None for no limitation.
        :param kwargs: Inherited arguments from the BaseBone.
        """
        super().__init__(**kwargs)
        if maxLength is not None and maxLength <= 0:
            raise ValueError("maxLength must be a positive integer or None")
        self.caseSensitive = caseSensitive
        self.maxLength = maxLength

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        if not self.caseSensitive and parentIndexed:
            return {"val": value, "idx": value.lower() if isinstance(value, str) else None}
        return value

    def singleValueUnserialize(self, value):
        if isinstance(value, dict) and "val" in value:
            return value["val"]
        elif value:
            return str(value)
        else:
            return ""

    def getEmptyValue(self):
        return ""

    def isEmpty(self, value):
        if not value:
            return True

        return not bool(str(value).strip())

    def isInvalid(self, value):
        """
        Returns None if the value would be valid for
        this bone, an error-message otherwise.
        """
        if self.maxLength is not None and len(value) > self.maxLength:
            return "Maximum length exceeded"
        return None

    def singleValueFromClient(self, value, skel, name, origData):
        value = utils.escapeString(value, self.maxLength)
        if not (err := self.isInvalid(value)):
            return value, None
        return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

    def buildDBFilter(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: Dict,
        prefix: Optional[str] = None
    ) -> db.Query:
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
                lang = current.language.get()  # currentSession.getLanguage()
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
                    lang = current.language.get()  # currentSession.getLanguage()
                    if not lang or lang not in self.languages:
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
        result = set()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            for line in str(value).splitlines():  # TODO: Can a StringBone be multiline?
                for word in line.split(" "):
                    result.add(word.lower())
        return result

    def getUniquePropertyIndexValues(self, skel, name: str) -> List[str]:
        if self.languages:
            # Not yet implemented as it's unclear if we should keep each language distinct or not
            raise NotImplementedError()

        return super().getUniquePropertyIndexValues(skel, name)

    def structure(self) -> dict:
        ret = super().structure() | {
            "maxlength": self.maxLength
        }
        return ret
