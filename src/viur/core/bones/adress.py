import hashlib
import json
import logging
import typing as t
import urllib.parse
import urllib.request

from .record import RecordBone
from .string import StringBone
from .selectcountry import SelectCountryBone
from .spatial import SpatialBone
from ..skeleton.relskel import RelSkel
from .. import db

CACHE_KIND = "viur-adressbone-geocache"


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

    def after_from_client(self, skel, name, errors):
        value = skel[name]
        if value is not None:
            coords = self.geocode(value)
            if coords:
                value["coordinates"] = coords

    @staticmethod
    def _cache_key(params: str) -> db.Key:
        digest = hashlib.sha256(params.encode()).hexdigest()
        return db.Key(CACHE_KIND, digest)

    @staticmethod
    def geocode(skel: RelSkel) -> tuple[float, float] | None:
        street = f"{skel['street'] or ''} {skel['number'] or ''}".strip()
        params = urllib.parse.urlencode({
            "street": street,
            "postalcode": skel["zip"] or "",
            "city": skel["city"] or "",
            "country": skel["country"] or "",
            "format": "json",
            "limit": 1,
        })
        cache_key = AdressBone._cache_key(params)
        try:
            cached = db.get(cache_key)
            if cached is not None:
                return cached["lat"], cached["lng"]
            req = urllib.request.Request(
                f"https://nominatim.openstreetmap.org/search?{params}",
                headers={"User-Agent": "viur-adressbone/1.0 (viur.dev)"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read())
            if not data:
                return None
            lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
            entity = db.Entity(cache_key)
            entity["lat"] = lat
            entity["lng"] = lng
            db.put(entity)
            return lat, lng
        except Exception as e:
            logging.error(f"AdressBone: Nominatim geocoding failed with {e=}")
        return None
