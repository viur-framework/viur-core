RandomSliceBone
^^^^^^^^^^^^^^^

Our randomSliceBone simulates the orderby=random known from traditional RDBM Systems ontop of the datastore.
As the datastore does't support retrieving a random set of elements, we'll use the following approach to provide
this functionality.

If used, this bone writes a randomly chosen float from [0..1) along with the entry saved to the datastore.
Each time the skeleton is updated, a new random value is shuffled for that entry.
If we assume we have 15 entries in the datastore, the following image shows a possible distribution of these randomly
chosen values.

  .. figure:: /images/implementationdetails/randomSliceBone1.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Example representation of our random float value from the 15 Entries


Now, if a randomly chosen set of entries is requested by fetching a list with orderby=random
(and we'll assume amount=2 in this example), this bone shuffles a new random-value and queries the datastore for
elements that are closest to that value. To increase randomness, it's possible to shuffle multiple values and query
the datastore for elements near them. In the following image, we have diced two values and query the datastore for the
four closest elements on each.

 .. figure:: /images/implementationdetails/randomSliceBone2.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Example from above, with 2 randomly chosen slices and the entites we've fetched from the datastore



So for each slice 2 subqueries are send to the datastore: Entities, which random property values are <= our random value
(sorted descending), and entities which random property is > our random value (sorted ascending).


To increase the randomness further, we've now fetched four times the amount of entities requested (requested amount
is two, we've fetched 8 in total). So we can now simply return a random selection of these eight entries we've fetched.


 .. figure:: /images/implementationdetails/randomSliceBone3.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Entites actually returned in black



.. Note::
    In the default configuration of two slices and a sliceSize of 0.5, each request using orderby=random uses 2 times
    more datastore quota than a normal request. This can be reduced to a single db read overhead by setting slices=1
    and sliceSize=0.5. But this also reduces the actual randomness of the entities returned. On the other hand it's
    possible to increase the randomness by increasing slices and/or sliceSize (which will use up more quota in turn).
