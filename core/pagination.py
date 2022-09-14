from hashlib import sha256
from typing import List, Optional

from viur.core import db, utils


class Pagination:
    """
    This module provides efficient pagination for a small specified set of queries.
    The datastore does not provide an efficient method for skipping N number of entities. This prevents
    the usual navigation over multiple pages (in most cases - like a google search - the user expects a list
    of pages (e.g. 1-10) on the bottom of each page with direct access to these pages). With the datastore and it's
    cursors, the most we can provide is a next-page & previous-page link using cursors. This module provides an
    efficient method to provide these direct-access page links under the condition that only a few, known-in-advance
    queries will be run. This is typically the case for forums, where there is only one query per thread (it's posts
    ordered by creation date) and one for the threadlist (it's threads, ordered by changedate).

    To use this module, create an instance of this index-manager on class-level (setting page_size & max_pages).
    Then call :meth:get_pages with the query you want to retrieve the cursors for the individual pages for. This
    will return one start-cursor per available page that can then be used to create urls that point to the specific
    page. When the entities returned by the query change (eg a new post is added), call :meth:refresh_index for
    each affected query.

    .. Note::

        The refreshAll Method is missing - intentionally. Whenever data changes you have to call
        refresh_index for each affected Index. As long as you can name them, their number is
        limited and this module can be efficiently used.
    """

    _db_type = "viur_pagination"

    def __init__(self, page_size: int = 10, max_pages: int = 100):
        """
        :param page_size: How many entities shall fit on one page
        :param max_pages: How many pages are build.
            Items become unreachable if the amount of items exceeds
            page_size*max_pages (i.e. if a forum-thread has more than
            page_size*max_pages Posts, Posts after that barrier won't show up).
        """
        self.page_size = page_size
        self.max_pages = max_pages

    def key_from_query(self, query: db.Query) -> str:
        """
            Derives a unique Database-Key from a given query.
            This Key is stable regardless in which order the filter have been applied

            :param query: Query to derive key from
            :returns: The unique key derived
        """
        if not isinstance(query, db.Query):
            raise TypeError(
                f"Expected a query. Got {query!r} of type {type(query)!r}")
        if isinstance(query.queries, list):
            raise NotImplementedError  # TODO: Can we handle this case? How?
        elif query.queries is None:
            raise ValueError("The query has no queries!")
        orig_filter = [(x, y) for x, y in query.queries.filters.items()]
        for field, sort_order in query.queries.orders:
            orig_filter.append((f"{field} =", sort_order))
        if query.queries.limit:
            orig_filter.append(("__pagesize =", self.page_size))
        orig_filter.sort(key=lambda sx: sx[0])
        filter_key = "".join("%s%s" % (x, y) for x, y in orig_filter)
        return sha256(filter_key.encode()).hexdigest()

    def get_or_build_index(self, orig_query: db.Query) -> List[str]:
        """
        Builds a specific index based on origQuery
        AND local variables (self.page_size and self.max_pages)
        Returns a list of starting-cursors for each page.
        You probably shouldn't call this directly. Use cursor_for_query.

        :param orig_query: Query to build the index for
        """
        key = self.key_from_query(orig_query)

        # We don't have it cached - try to load it from DB
        index = db.Get(db.Key(self._db_type, key))
        if index is not None:
            return index["data"]

        # We don't have this index yet... Build it
        query = orig_query.clone()
        cursors = [None]
        while len(cursors) < self.max_pages:
            query_res = query.run(limit=self.page_size)
            if not query_res:
                # This cursor returns no data, remove it
                cursors.pop()
                break
            if query.getCursor() is None:
                # We reached the end of our data
                break
            cursors.append(query.getCursor())
            query.setCursor(query.getCursor())

        entry = db.Entity(db.Key(self._db_type, key))
        entry["data"] = cursors
        entry["creationdate"] = utils.utcNow()
        db.Put(entry)
        return cursors

    def cursor_for_query(self, query: db.Query, page: int) -> Optional[str]:
        """
        Returns the starting-cursor for the given query and page using an index.

        .. WARNING:

            Make sure the maximum count of different queries are limited!
            If an attacker can choose the query freely, he can consume a lot
            datastore quota per request!

        :param query: Query to get the cursor for
        :param page: Page the user wants to retrieve
        :returns: Cursor or None if no cursor is applicable
        """
        page = int(page)
        pages = self.get_or_build_index(query)
        if 0 <= page < len(pages):
            return pages[page]
        else:
            return None

    def get_pages(self, query: db.Query) -> List[str]:
        """
        Returns a list of all starting-cursors for this query.
        The first element is always None as the first page doesn't
        have any start-cursor
        """
        return self.get_or_build_index(query)

    def refresh_index(self, query: db.Query) -> None:
        """
        Refreshes the Index for the given query
        (Actually it removes it from the db, so it gets rebuild on next use)

        :param query: Query for which the index should be refreshed
        """
        key = self.key_from_query(query)
        db.Delete(db.Key(self._db_type, key))
