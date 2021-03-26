================
Data consistency
================

Unlike traditional `LAMP systems`_, consistency is handled differently on the `GAE`_. There are three different causes
for inconsistency when using ViUR on the GAE_.

.. _LAMP systems: https://en.wikipedia.org/wiki/LAMP_(software_bundle)
.. _GAE: https://appengine.google.com

This chapter will explain the different types of inconsistency's that may appear on the GAE and ViUR. While we had never
noticed one in the wild, you should be aware of them, know when they can appear and whats needed in case you absolutely
need to avoid them

Datastore
---------
The datastore offers 2 kinds of queries, providing different consistency constrains. The ''normal`` and fast queries
provide only eventual consistency. This means that changes made to one entity might not be visible instantly.
To ensure that your queries catch recent changes, ancestor queries are needed.
However, they're slower and have other constrains, so they are not used in ViUR by default. You'll need to set the
ancestor yourself on each query that needs to be consistent.

Consequences/Example:
Imagine you have a list of objects, and provide a list filtered by the object's color.
Now you change the color of one of these objects from ''red`` to ''blue``.
Due to the inconsistency, it's possible for that object to still appear in the list of ''red`` objects
(instead of the ''blue`` ones) for a short (usually a fraction of second) period of time after the change
has been committed to the datastore.

Data cache
----------
ViUR tries to optimize speed and resource usage by utilizing the Memcache to cache database queries.
Unfortunately, this introduces another type of inconsistency. In rare cases it's possible that the entry in
the Memcache is updated before the indexes in the datastore can catch up (or the other way round).

Consequences/Example:
Given the example introduced before, it's possible for the recently changed entry to still show up in the list
of ''red`` ones, but will list itself as ''blue`` already. Or it may show in lists of ''blue`` ones while still being
seen as a ''red`` one.
In fact, it's possible that a db query by color returns results with entries of a different color,
if that entries' color has recently been changed.
As the datastore usually applies these changes in less than a second, this is very unlikely to happen,
but it's possible. You can configure ViURs db-caching by setting :obj:`core.config.conf['viur.db.caching']`.
A value of '2' (the default) means cache as much as possible, where it's possible for this inconsistency to appear
under rare circumstances. '1' means less aggressive cache, where queries aren't served from Memcache, so that this
inconsistency cannot happen. Setting this value to '0' means no caching at all (not recommend).

Relations
---------
Relations are a core feature offered by ViUR. But as the datastore is non-relational,
offering relations on top of a non-relational datastore is a fairly complex task. To maintain quick response times,
ViUR doesn't search and update relations when an entry is updated. Instead, a deferred task is kicked off
which will update these relations in the background. Through depending on the current load of your application, these
tasks usually catch up within a few seconds.

Consequences/Example:
Within this time, a search by such a relation might return stale results.
Assume that you have a relation from user to the colored objects from the first example (e.g. a user liked that object).
If that relation is part of the user skeleton, this problem arises.
So if the color of an object is changed, the query ''all users who like a red object`` will still include that object
until the background task finished updating the relations - though the object returned will already have blue as value
for the color property.
Note that this does not happen if the relation is part of that objects (i.e if the objects reference the user who liked it).
Rule of thumb: Relations which are part of the kind which got updated are updated *instantly* (see below).
Relations referencing that kind from another kind are updated later.


The second inconsistency that may appear when using multiple=True relations is caused by the fact that only the
entry itself (and some locking entries absolutely required to be consistent) are updated inside the transaction that
writes changed data to the datastore. The search-indexes for these relations are updated **after** the transaction
succeeded (but they are updated in the same request, it's not been deferred). So it's possible to see the updated values
from the transaction while queries using such relations are still being filtered by the old values.
Sadly, there is no easy way around this. It may be possible to update certain relational search objects inside the
transaction, but you would have to implement this yourself.


Request cache
-------------
ViUR offers a request cache, to speed up serving complex pages. This cache is not enabled by default,
as it has to be tightly integrated into the individual application. As flushing that cache happens asynchronous
in the background, it's possible to have inconsistency between two sequential requests.

Consequences/Example:
Given our example this means that our recently changed object might appear in both (red and blue) lists
(or in no list at all) for a short time-frame.