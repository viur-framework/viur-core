from abstract import ViURTestCase


class TestAdressBoneInit(ViURTestCase):

    def test_default_using_is_adress_rel_skel(self):
        from viur.core.bones.adress import AdressBone, AdressRelSkel
        bone = AdressBone()
        self.assertIs(AdressRelSkel, bone.using)

    def test_type_is_record_adress(self):
        from viur.core.bones.adress import AdressBone
        bone = AdressBone()
        self.assertEqual("record.adress", bone.type)

    def test_default_format_contains_address_fields(self):
        from viur.core.bones.adress import AdressBone
        bone = AdressBone()
        self.assertIn("street", bone.format)
        self.assertIn("city", bone.format)

    def test_custom_using_overrides_default(self):
        from viur.core.bones.adress import AdressBone
        from viur.core.skeleton.relskel import RelSkel
        from viur.core.bones import StringBone

        class CustomSkel(RelSkel):
            name = StringBone()

        bone = AdressBone(using=CustomSkel)
        self.assertIs(CustomSkel, bone.using)


class TestAdressRelSkel(ViURTestCase):

    def test_has_all_fields(self):
        from viur.core.bones.adress import AdressRelSkel
        bone_names = list(AdressRelSkel.__boneMap__.keys())
        for field in ("street", "number", "zip", "city", "country", "coordinates"):
            self.assertIn(field, bone_names)

    def test_street_is_required(self):
        from viur.core.bones.adress import AdressRelSkel
        from viur.core.bones import StringBone
        bone = AdressRelSkel.__boneMap__["street"]
        self.assertIsInstance(bone, StringBone)
        self.assertTrue(bone.required)

    def test_city_is_required(self):
        from viur.core.bones.adress import AdressRelSkel
        from viur.core.bones import StringBone
        bone = AdressRelSkel.__boneMap__["city"]
        self.assertIsInstance(bone, StringBone)
        self.assertTrue(bone.required)

    def test_country_is_select_country_bone(self):
        from viur.core.bones.adress import AdressRelSkel
        from viur.core.bones import SelectCountryBone
        self.assertIsInstance(AdressRelSkel.__boneMap__["country"], SelectCountryBone)

    def test_coordinates_is_spatial_bone_with_world_bounds(self):
        from viur.core.bones.adress import AdressRelSkel
        from viur.core.bones import SpatialBone
        bone = AdressRelSkel.__boneMap__["coordinates"]
        self.assertIsInstance(bone, SpatialBone)
        self.assertEqual((-90, 90), bone.boundsLat)
        self.assertEqual((-180, 180), bone.boundsLng)

    def test_number_zip_country_coordinates_not_required(self):
        from viur.core.bones.adress import AdressRelSkel
        for field in ("number", "zip", "country", "coordinates"):
            bone = AdressRelSkel.__boneMap__[field]
            self.assertFalse(bone.required, f"{field} should not be required")
