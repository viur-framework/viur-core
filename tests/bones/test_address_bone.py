from unittest.mock import MagicMock, patch

from abstract import ViURTestCase


class TestAddressBoneInit(ViURTestCase):

    def test_default_using_is_address_rel_skel(self):
        from viur.core.bones.address import AddressBone, AddressRelSkel
        bone = AddressBone()
        self.assertIs(AddressRelSkel, bone.using)

    def test_type_is_record_address(self):
        from viur.core.bones.address import AddressBone
        bone = AddressBone()
        self.assertEqual("record.address", bone.type)

    def test_default_format_contains_address_fields(self):
        from viur.core.bones.address import AddressBone
        bone = AddressBone()
        self.assertIn("street_name", bone.format)
        self.assertIn("city", bone.format)

    def test_custom_using_overrides_default(self):
        from viur.core.bones.address import AddressBone
        from viur.core.skeleton.relskel import RelSkel
        from viur.core.bones import StringBone

        class CustomSkel(RelSkel):
            name = StringBone()

        bone = AddressBone(using=CustomSkel)
        self.assertIs(CustomSkel, bone.using)


class TestAddressRelSkel(ViURTestCase):

    def test_has_all_fields(self):
        from viur.core.bones.address import AddressRelSkel
        bone_names = list(AddressRelSkel.__boneMap__.keys())
        for field in ("street_name", "street_number", "address_addition", "zip_code", "city", "country", "coordinates"):
            self.assertIn(field, bone_names)

    def test_street_name_is_required(self):
        from viur.core.bones.address import AddressRelSkel
        from viur.core.bones import StringBone
        bone = AddressRelSkel.__boneMap__["street_name"]
        self.assertIsInstance(bone, StringBone)
        self.assertTrue(bone.required)

    def test_city_is_required(self):
        from viur.core.bones.address import AddressRelSkel
        from viur.core.bones import StringBone
        bone = AddressRelSkel.__boneMap__["city"]
        self.assertIsInstance(bone, StringBone)
        self.assertTrue(bone.required)

    def test_country_is_select_country_bone(self):
        from viur.core.bones.address import AddressRelSkel
        from viur.core.bones import SelectCountryBone
        self.assertIsInstance(AddressRelSkel.__boneMap__["country"], SelectCountryBone)

    def test_coordinates_is_spatial_bone_with_world_bounds(self):
        from viur.core.bones.address import AddressRelSkel
        from viur.core.bones import SpatialBone
        bone = AddressRelSkel.__boneMap__["coordinates"]
        self.assertIsInstance(bone, SpatialBone)
        self.assertEqual((-90, 90), bone.boundsLat)
        self.assertEqual((-180, 180), bone.boundsLng)

    def test_optional_fields_not_required(self):
        from viur.core.bones.address import AddressRelSkel
        for field in ("street_number", "address_addition", "zip_code", "country", "coordinates"):
            bone = AddressRelSkel.__boneMap__[field]
            self.assertFalse(bone.required, f"{field} should not be required")


class TestAddressBoneGeocode(ViURTestCase):

    def _make_skel(
        self,
        street_name="Chaussée de Liège",
        street_number="53",
        city="Welkenraedt",
        zip_code="4841",
        country="be"
    ):
        from viur.core.bones.address import AddressRelSkel
        skel = AddressRelSkel()
        skel["street_name"] = street_name
        skel["street_number"] = street_number
        skel["city"] = city
        skel["zip_code"] = zip_code
        skel["country"] = country
        skel["coordinates"] = None
        return skel

    def _make_nominatim_response(self, lat="50.671720", lon="5.912884"):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"lat": lat, "lon": lon}]
        return mock_response

    def test_geocode_fills_coordinates_when_missing(self):
        from viur.core.bones.address import AddressBone
        bone = AddressBone()
        skel = self._make_skel()

        with patch("viur.core.bones.address.db.get", return_value=None), \
                patch("viur.core.bones.address.db.put"), \
                patch("viur.core.bones.address.db.Entity", return_value={}), \
                patch("viur.core.bones.address.requests.get",
                      return_value=self._make_nominatim_response()):
            result = bone.geocode(skel)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[0], 50.671720)
        self.assertAlmostEqual(result[1], 5.912884)

    def test_geocode_returns_none_on_empty_nominatim_response(self):
        from viur.core.bones.address import AddressBone
        bone = AddressBone()
        skel = self._make_skel(street_name="Unknown Street", city="Nowhere")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("viur.core.bones.address.db.get", return_value=None), \
                patch("viur.core.bones.address.requests.get", return_value=mock_response):
            result = bone.geocode(skel)

        self.assertIsNone(result)

    def test_geocode_returns_none_on_non_200_status(self):
        from viur.core.bones.address import AddressBone
        bone = AddressBone()
        skel = self._make_skel()

        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch("viur.core.bones.address.db.get", return_value=None), \
                patch("viur.core.bones.address.requests.get", return_value=mock_response):
            result = bone.geocode(skel)

        self.assertIsNone(result)
        mock_response.json.assert_not_called()

    def test_geocode_returns_none_on_network_error(self):
        from viur.core.bones.address import AddressBone
        bone = AddressBone()
        skel = self._make_skel()

        with patch("viur.core.bones.address.db.get", return_value=None), \
                patch("viur.core.bones.address.requests.get", side_effect=OSError("network error")):
            result = bone.geocode(skel)

        self.assertIsNone(result)

    def test_geocode_cache_hit_skips_nominatim(self):
        from viur.core.bones.address import AddressBone
        bone = AddressBone()
        skel = self._make_skel()

        cached_entity = {"lat": 50.671720, "lng": 5.912884}

        with patch("viur.core.bones.address.db.get", return_value=cached_entity), \
                patch("viur.core.bones.address.requests.get") as mock_get:
            result = bone.geocode(skel)

        mock_get.assert_not_called()
        self.assertAlmostEqual(result[0], 50.671720)
        self.assertAlmostEqual(result[1], 5.912884)

    def test_geocode_cache_miss_stores_result(self):
        from viur.core.bones.address import AddressBone
        bone = AddressBone()
        skel = self._make_skel()

        mock_entity = {}
        mock_put = MagicMock()

        with patch("viur.core.bones.address.db.get", return_value=None), \
                patch("viur.core.bones.address.db.put", mock_put), \
                patch("viur.core.bones.address.db.Entity", return_value=mock_entity), \
                patch("viur.core.bones.address.requests.get",
                      return_value=self._make_nominatim_response()):
            bone.geocode(skel)

        mock_put.assert_called_once()
        self.assertAlmostEqual(mock_entity["lat"], 50.671720)
        self.assertAlmostEqual(mock_entity["lng"], 5.912884)
