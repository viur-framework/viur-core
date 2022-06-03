# -*- coding: utf-8 -*-
import json
from datetime import datetime
from hashlib import sha256
from typing import List, Optional
from viur.core import db


class IndexMannager:
	"""
		This module provides efficient pagination for a small specified set of queries.
		The datastore does not provide an efficient method for skipping N number of entities. This prevents
		the usual navigation over multiple pages (in most cases - like a google search - the user expects a list
		of pages (eg. 1-10) on the bottom of each page with direct access to these pages). With the datastore and it's
		cursors, the most we can provide is a next-page & previous-page link using cursors. This module provides an
		efficient method to provide these direct-access page links under the condition that only a few, known-in-advance
		queries will be run. This is typically the case for forums, where there is only one query per thread (it's posts
		ordered by creation date) and one for the threadlist (it's threads, ordered by changedate).

		To use this module, create an instance of this index-manager on class-level (setting pageSize & maxPages).
		Then call :meth:getPages with the query you want to retrieve the cursors for the individual pages for. This
		will return one start-cursor per available page that can then be used to create urls that point to the specific
		page. When the entities returend by the query change (eg a new post is added), call :meth:refreshIndex for
		each affected query.

		.. Note::

			The refreshAll Method is missing - intentionally. Whenever data changes you have to call
			refreshIndex for each affected Index. As long as you can name them, their number is
			limited and this module can be efficiently used.

	"""

	_dbType = "viur_indexes"

	def __init__(self, pageSize: int = 10, maxPages: int = 100):
		"""
			:param pageSize: How many entities shall fit on one page
			:param maxPages: How many pages are build. Items become unreachable if the amount of items
				exceed pageSize*maxPages (ie. if a forum-thread has more than pageSize*maxPages Posts, Posts
				after that barrier won't show up).
		"""
		self.pageSize = pageSize
		self.maxPages = maxPages

	def keyFromQuery(self, query: db.Query) -> str:
		"""
			Derives a unique Database-Key from a given query.
			This Key is stable regardless in which order the filter have been applied

			:param query: Query to derive key from
			:returns: The unique key derived
		"""
		assert isinstance(query, db.Query)
		origFilter = [(x, y) for x, y in query.getFilter().items()]
		for k, v in query.getOrders():
			origFilter.append(("__%s =" % k, v))
		if query.amount:
			origFilter.append(("__pagesize =", self.pageSize))
		origFilter.sort(key=lambda sx: sx[0])
		filterKey = "".join(["%s%s" % (x, y) for x, y in origFilter])
		return sha256(filterKey).hexdigest()

	def getOrBuildIndex(self, origQuery:db.Query) -> List[str]:
		"""
			Builds a specific index based on origQuery AND local variables (self.indexPage and self.indexMaxPage)
			Returns a list of starting-cursors for each page.
			You probably shouldn't call this directly. Use cursorForQuery.

			:param origQuery: Query to build the index for
			:returns: []
		"""
		key = self.keyFromQuery(origQuery)
		# We don't have it cached - try to load it from DB
		try:
			index = db.Get(db.Key.from_path(self._dbType, key))
			res = json.loads(index["data"])
			return res
		except db.EntityNotFoundError:  # Its not in the datastore, too
			pass
		# We don't have this index yet.. Build it
		# Clone the original Query
		queryRes = origQuery.clone().datastoreQuery.Run(limit=self.maxPages * self.pageSize)
		# Build-Up the index
		res = list()
		previousCursor = None  # The first page dosnt have any cursor

		# enumerate is slightly faster than a manual loop counter
		for counter, discardedKey in enumerate(queryRes):
			if counter % self.pageSize == 0:
				res.append(previousCursor)
			if counter % self.pageSize == (self.pageSize - 1):
				previousCursor = str(queryRes.cursor().urlsafe())

		if not len(res):  # Ensure that the first page exists
			res.append(None)

		entry = db.Entity(self._dbType, name=key)
		entry["data"] = json.dumps(res)
		entry["creationdate"] = datetime.now()
		db.Put(entry)
		return res

	def cursorForQuery(self, query: db.Query, page:int) -> Optional[str]:
		"""
			Returns the starting-cursor for the given query and page using an index.

			.. WARNING:

				Make sure the maximum count of different querys are limited!
				If an attacker can choose the query freely, he can consume a lot
				datastore quota per request!

			:param query: Query to get the cursor for
			:param page: Page the user wants to retrieve
			:returns: Cursor or None if no cursor is applicable
		"""
		page = int(page)
		pages = self.getOrBuildIndex(query)
		if 0 < page < len(pages):
			return db.Cursor(urlsafe=pages[page])
		else:
			return None

	def getPages(self, query: db.Query) -> List[str]:
		"""
			Returns a list of all starting-cursors for this query.
			The first element is always None as the first page doesn't
			have any start-cursor
		"""
		return self.getOrBuildIndex(query)

	def refreshIndex(self, query: db.Query):
		"""
			Refreshes the Index for the given query
			(Actually it removes it from the db so it gets rebuild on next use)

			:param query: Query for which the index should be refreshed
			:type query: db.Query
		"""
		key = self.keyFromQuery(query)
		try:
			db.Delete(db.Key.from_path(self._dbType, key))
		except:
			pass
