import typing as t
from itertools import chain
from .. import db
from ..config import conf


class DatabaseAdapter:
    """
    Adapter class used to bind or use other databases and hook operations when working with a Skeleton.
    """

    providesFulltextSearch: bool = False
    """Set to True if we can run a fulltext search using this database."""

    fulltextSearchGuaranteesQueryConstrains = False
    """Are results returned by `meth:fulltextSearch` guaranteed to also match the databaseQuery"""

    providesCustomQueries: bool = False
    """Indicate that we can run more types of queries than originally supported by datastore"""

    def prewrite(self, skel: "SkeletonInstance", is_add: bool, change_list: t.Iterable[str] = ()):
        """
        Hook being called on a add, edit or delete operation before the skeleton-specific action is performed.

        The hook can be used to modifiy the skeleton before writing.
        The raw entity can be obainted using `skel.dbEntity`.

        :param action: Either contains "add", "edit" or "delete", depending on the operation.
        :param skel: is the skeleton that is being read before written.
        :param change_list: is a list of bone names which are being changed within the write.
        """
        pass

    def write(self, skel: "SkeletonInstance", is_add: bool, change_list: t.Iterable[str] = ()):
        """
        Hook being called on a write operations after the skeleton is written.

        The raw entity can be obainted using `skel.dbEntity`.

        :param action: Either contains "add" or "edit", depending on the operation.
        :param skel: is the skeleton that is being read before written.
        :param change_list: is a list of bone names which are being changed within the write.
        """
        pass

    def delete(self, skel: "SkeletonInstance"):
        """
        Hook being called on a delete operation after the skeleton is deleted.
        """
        pass

    def fulltextSearch(self, queryString: str, databaseQuery: db.Query) -> list[db.Entity]:
        """
        If this database supports fulltext searches, this method has to implement them.
        If it's a plain fulltext search engine, leave 'prop:fulltextSearchGuaranteesQueryConstrains' set to False,
        then the server will post-process the list of entries returned from this function and drop any entry that
        cannot be returned due to other constrains set in 'param:databaseQuery'. If you can obey *every* constrain
        set in that Query, we can skip this post-processing and save some CPU-cycles.
        :param queryString: the string as received from the user (no quotation or other safety checks applied!)
        :param databaseQuery: The query containing any constrains that returned entries must also match
        :return:
        """
        raise NotImplementedError


class ViurTagsSearchAdapter(DatabaseAdapter):
    """
    This Adapter implements a simple fulltext search on top of the datastore.

    On skel.write(), all words from String-/TextBones are collected with all *min_length* postfixes and dumped
    into the property `viurTags`. When queried, we'll run a prefix-match against this property - thus returning
    entities with either an exact match or a match within a word.

    Example:
        For the word "hello" we'll write "hello", "ello" and "llo" into viurTags.
        When queried with "hello" we'll have an exact match.
        When queried with "hel" we'll match the prefix for "hello"
        When queried with "ell" we'll prefix-match "ello" - this is only enabled when substring_matching is True.

    We'll automatically add this adapter if a skeleton has no other database adapter defined.
    """
    providesFulltextSearch = True
    fulltextSearchGuaranteesQueryConstrains = True

    def __init__(self, min_length: int = 2, max_length: int = 50, substring_matching: bool = False):
        super().__init__()
        self.min_length = min_length
        self.max_length = max_length
        self.substring_matching = substring_matching

    def _tags_from_str(self, value: str) -> set[str]:
        """
        Extract all words including all min_length postfixes from given string
        """
        res = set()

        for tag in value.split(" "):
            tag = "".join([x for x in tag.lower() if x in conf.search_valid_chars])

            if len(tag) >= self.min_length:
                res.add(tag)

                if self.substring_matching:
                    for i in range(1, 1 + len(tag) - self.min_length):
                        res.add(tag[i:])

        return res

    def prewrite(self, skel: "SkeletonInstance", *args, **kwargs):
        """
        Collect searchTags from skeleton and build viurTags
        """
        tags = set()

        for name, bone in skel.items():
            if bone.searchable:
                tags = tags.union(bone.getSearchTags(skel, name))

        skel.dbEntity["viurTags"] = list(
            chain(*[self._tags_from_str(tag) for tag in tags if len(tag) <= self.max_length])
        )

    def fulltextSearch(self, queryString: str, databaseQuery: db.Query) -> list[db.Entity]:
        """
        Run a fulltext search
        """
        keywords = list(self._tags_from_str(queryString))[:10]
        resultScoreMap = {}
        resultEntryMap = {}

        for keyword in keywords:
            qryBase = databaseQuery.clone()
            for entry in qryBase.filter("viurTags >=", keyword).filter("viurTags <", keyword + "\ufffd").run():
                if entry.key not in resultScoreMap:
                    resultScoreMap[entry.key] = 1
                else:
                    resultScoreMap[entry.key] += 1
                if entry.key not in resultEntryMap:
                    resultEntryMap[entry.key] = entry

        resultList = [(k, v) for k, v in resultScoreMap.items()]
        resultList.sort(key=lambda x: x[1], reverse=True)

        return [resultEntryMap[x[0]] for x in resultList[:databaseQuery.queries.limit]]
