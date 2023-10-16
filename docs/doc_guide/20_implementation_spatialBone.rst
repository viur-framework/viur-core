SpatialBone
^^^^^^^^^^^^

The (Geo-)spatial Bone implements proximity searches. It provides a somewhat efficient way to retrieve entities,
which are closest to a given point. Our algorithm is based on two assumptions:
  1. The region we're searching is small enough to ignore errors introduced by transferring the spherical earth surface
     into a flat map. This means you cannot search the whole world. Your data must be limited to a
     region/country/continent.
  2. The region is larger than the actual area of interest. This means that there's a predefined limit on distance, in
     which results are useful. It's okay to discard results outside of this limit, even if they would have been the
     closest ones.
     .. Example::
           If you query your application to the next Pub, you might expect results within a range of 100km. A Pub in
           500km distance would probably be useless to you - even if it would be the closest one, so it's okay if this
           algorithm doesn't find it.

Use this bone only if your use-case meet these assumptions!

Lets assume we have a very sparse map, got a point somewhere inside and want to get the entries close around.

 .. figure:: /images/implementationdetails/spatialBone1.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    A sparse map, our position and the elements close around

Our algorithm uses a sweepline to fetch the points close to the given position. So one subquery is performed for each
possible direction on the map (North/South/East/West), which fetches the next n Points in the given direction

Lets assume we have a very sparse map, got a point somewhere inside and want to get the entries close around.

 .. figure:: /images/implementationdetails/spatialBone2.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Start of the first Sweepline

 .. figure:: /images/implementationdetails/spatialBone3.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    End of the first Sweepline after 5 processed points

 .. figure:: /images/implementationdetails/spatialBone4.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Final result after running all four sweeplines. Processed points in green, Points that have been seen multiple
    times in yellow.

While this simple approach catches all points in the close surrounding, is also catches points far outside the
area of intrest.

 .. figure:: /images/implementationdetails/spatialBone5.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Points that have been processed, but that are way too far from the area of interest

This gets even worse if the map is more dense populated.

 .. figure:: /images/implementationdetails/spatialBone6.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Processed points in a more dense map


This is where the second assumpion comes in hand.
We split the map into alleys that are three times wider than the limit on distance that we'll consider. So if your
use-case requires a distance up to 100km, a alley will be roughly 300km width/height.
Allys will overlap (an ally will start each 100km)

 .. figure:: /images/implementationdetails/spatialBone7.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    First two overlapping alleys

This has two implications. First, every point lies within up to three allys. And there is always at least one ally,
which boarders have at least 100km distance to the given point.

 .. figure:: /images/implementationdetails/spatialBone8.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Ally, which borders are at least 100km distance to the given point

Now its possible to limit the sweepline to points inside this special ally. If apply this alleys on both directions
we can limit each sweepline to ignore points outside the area of interest.

 .. figure:: /images/implementationdetails/spatialBone9.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Both allys with the first sweepline executed

After running all four sweeplines we can sort the fetched results by distance and we can determine the guranteed
correctness, ie. the distance for which we can prove that there can't be any points we've missed.
Our algorithm may return points further away, but there might be points in between which we could have missed.

 .. figure:: /images/implementationdetails/spatialBone10.png
    :align: center
    :alt: Implemenation-Details for randomSliceBone
    :figclass: align-center

    Size of the minimum guranteed correctness distance




