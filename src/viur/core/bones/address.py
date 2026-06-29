import hashlib
import logging
import typing as t
import urllib.parse

import requests

from .record import RecordBone
from .string import StringBone
from .selectcountry import SelectCountryBone
from .spatial import SpatialBone
from ..skeleton.relskel import RelSkel
from .. import db, i18n
from ..data.zip_patterns import ZIP_CODE_PATTERNS

CACHE_KIND = "viur-addressbone-geocache"


class AddressRelSkel(RelSkel):
    street_name = StringBone(descr="Street", required=True)
    street_number = StringBone(descr="House number")
    address_addition = StringBone(descr="Address addition")
    zip_code = StringBone(
        descr="ZIP / Postal code",
        params={
            "pattern": ZIP_CODE_PATTERNS,
            "pattern-error": i18n.translate(
                "viur.core.bones.address.zip_code.invalid",
                defaultText="Invalid ZIP code",
            ),
        },
    )
    city = StringBone(descr="City", required=True)
    country = SelectCountryBone(descr="Country")
    coordinates = SpatialBone(
        descr="Coordinates",
        boundsLat=(-90, 90),
        boundsLng=(-180, 180),
        gridDimensions=(10, 10),
    )


class AddressBone(RecordBone):
    type = RecordBone.type + ".address"

    def __init__(
        self,
        *,
        using: t.Type[RelSkel] = AddressRelSkel,
        format: str = "$(street_name) $(street_number), $(zip_code) $(city)",
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
        street = f"{skel['street_name'] or ''} {skel['street_number'] or ''}".strip()
        params = {
            "street": street,
            "postalcode": skel["zip_code"] or "",
            "city": skel["city"] or "",
            "country": skel["country"] or "",
            "format": "json",
            "limit": 1,
        }
        cache_key = AddressBone._cache_key(urllib.parse.urlencode(params))
        try:
            cached = db.get(cache_key)
            if cached is not None:
                return cached["lat"], cached["lng"]
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers={"User-Agent": "viur-addressbone/1.0 (viur.dev)"},
                timeout=5,
            )
            if response.status_code != 200:
                logging.error(
                    f"AddressBone: Nominatim returned {response.status_code=}"
                )
                return None
            data = response.json()
            if not data:
                return None
            lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
            entity = db.Entity(cache_key)
            entity["lat"] = lat
            entity["lng"] = lng
            db.put(entity)
            return lat, lng
        except Exception as e:
            logging.error(f"AddressBone: Nominatim geocoding failed with {e=}")
        return None
