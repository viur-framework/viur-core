import typing as t

from .record import RecordBone
from .string import StringBone
from .selectcountry import SelectCountryBone
from .spatial import SpatialBone
from ..skeleton.relskel import RelSkel


class AdressRelSkel(RelSkel):
    street = StringBone(descr="Street", required=True)
    number = StringBone(descr="House number")
    zip = StringBone(descr="ZIP / Postal code")
    city = StringBone(descr="City", required=True)
    country = SelectCountryBone(descr="Country")
    coordinates = SpatialBone(
        descr="Coordinates",
        boundsLat=(-90, 90),
        boundsLng=(-180, 180),
        gridDimensions=(10, 10),
    )


class AdressBone(RecordBone):
    type = RecordBone.type + ".adress"

    def __init__(
        self,
        *,
        using: t.Type[RelSkel] = AdressRelSkel,
        format: str = "$(street) $(number), $(zip) $(city)",
        **kwargs,
    ):
        super().__init__(using=using, format=format, **kwargs)
