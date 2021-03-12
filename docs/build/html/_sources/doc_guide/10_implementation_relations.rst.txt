Relations
^^^^^^^^^
ViUR provides relations ontop of the non-relational datastore. In the following we'll explain how these relations are
implemented, what are the limits of this implementation and how much overhead it produces.


Filtering by properties of the referenced object
................................................
In ViUR, the actual implementation of relations depend on their type. For n:1 relations (i.e. an object is referring
*one* other object, we can simply copy the key (and everything from `refKeys`) into the referring object.
Assume we have a Skeleton "Product" consisting of a Name, Price and Category, with Categrory being a reference
to separate Skeleton "Category".


.. figure:: /images/implementationdetails/relations1.png
   :align: center
   :alt: Datamodel for this example of n:1 Relations
   :figclass: align-center

   Datamodel for this example of n:1 Relations

Lets assume that *key*, *available* and *active* is in the refKeys for that relation, so we can filter by products which
are in a category, which is available in a given region and generally active.
The final object written to the datastore for our product will be denormalized and look like the following


.. figure:: /images/implementationdetails/relations2.png
   :align: center
   :alt: Deserialized object in the datastore
   :figclass: align-center

   Deserialized object in the datastore


For n:m relations, this trick won't work. We would get a list of values for each referenced property, collecting all
values for that property from all referenced objects at once:

.. figure:: /images/implementationdetails/relations3.png
   :align: center
   :alt: Deserialized object in the datastore if we do n:m relations that way
   :figclass: align-center

   Deserialized object in the datastore if we do n:m relations that way

Now filtering by two properties of the referenced object could mess up. If we would filter by products which's category
is available in a given region *and* is active, the query would also return results, which have at least one active
category, and one (possibly *different*) category that's available in the given region.
So assume we've referenced two categories, one available in ["de","at","ch"] and being active, the other one not active
and available in ["gb", "us"], a query by active=True *and* available="gb" should not yield that entity as a result.
Yet, with this model, it does. So it's impossible to enforce that both requirements are meet by the same referenced category.


So for n:m relations, ViUR uses a different approach. We'll just store the Json-Encoded data from the referenced object
inside the referring object (so that fetching this object from the datastore contains all required information needed
for that relational bone, so we don't need to fetch the referenced entity also). To allow efficient filtering, we
create an new object in the datastore for each object referenced. We'll copy each property named in refKeys from the
referenced object into this new object (prefixed with "dest."), and each property named in parentKeys from the referring
object. Also the key of the referring and referred, their kinds and the name of the relationalBone are written to these
objects.

.. figure:: /images/implementationdetails/relations4.png
   :align: center
   :alt: Example of viur-relation objects
   :figclass: align-center

   Example of viur-relation objects

As a further optimisation, we'll store theses viur-relation objects under the referring object (the referring object
becomes the parent for these objects). So while querying using viur-relations, we'll only fetch the keys of these
objects machtech - never the viur-relations objects itself.
Having the keys, we can extract the keys of the parent from these keys and we can fetch them directly.


Updating values
...............
The second challenge is keeping this data consistent. As we copy data from the referenced object either into the
referring object or into itermediate viur-relation objects, we need a way to update this data if the referred object
is edited. As the viur-relation objects are updated each time the referring object is saved, we'll only need to cover
the case the referred object changes. So everytime a skeleton is updated, ViUR creates a deferred task, which checks
the viur-relation table if this entity is referenced by any other entity and updates these entries accordingly.
For n:1 relations, we could either check the data-models if there are any n:1 to the kind of the entry changed (which
might require several queries and indexes, or we could also write a small viur-relational entry. We've choosed to write
the viur-relational entry (just containing the keys and kinds of both entries and name of the bone) so we can save a lot
of compound indexes here. There are also some other tweaks to keep the overhead low, like writing a last update
timestamp into these objects, so an object won't get updated twice if it contains two seperate relations to the changed
object.

.. Warning::

      Theses updates don't cascade. If you name properties in refKeys, which have been copied in the referenced entity
      itself by another relation there, this won't be updated! So if you have
      Entry a --> relation1 --> Entry b --> relation2 --> Entry c
      and Entry c is updated, *only* data in Entry b gets updated too. If you have listed something like "relation2.name"
      in the refKeys of relation1, this will be missed and Entry a (or its viur-relation object's) will still contain
      the old value for relation2.name





