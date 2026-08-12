from abstract import ViURTestCase

_DummySkel = type("DummySkel", (), {})


def _country_bone(**kwargs):
    from viur.core.bones.selectcountry import SelectCountryBone
    bone = SelectCountryBone(**kwargs)
    bone.skel_cls = _DummySkel
    bone.name = "country"
    return bone


class TestSelectCountryBoneInit(ViURTestCase):

    def test_iso2_default(self):
        bone = _country_bone()
        self.assertIn("de", bone.values)
        self.assertIn("at", bone.values)
        self.assertIn("us", bone.values)

    def test_iso3_mode(self):
        from viur.core.bones.selectcountry import SelectCountryBone
        bone = _country_bone(codes=SelectCountryBone.ISO3)
        self.assertIn("deu", bone.values)
        self.assertIn("aut", bone.values)

    def test_dach_subgroup_iso2(self):
        bone = _country_bone(values="dach")
        keys = list(bone.values.keys())
        self.assertIn("de", keys)
        self.assertIn("at", keys)
        self.assertIn("ch", keys)
        self.assertNotIn("us", keys)

    def test_dach_subgroup_iso3(self):
        from viur.core.bones.selectcountry import SelectCountryBone
        bone = _country_bone(codes=SelectCountryBone.ISO3, values="dach")
        keys = list(bone.values.keys())
        self.assertIn("deu", keys)
        self.assertIn("aut", keys)
        self.assertIn("che", keys)

    def test_eu_subgroup(self):
        bone = _country_bone(values="eu")
        keys = list(bone.values.keys())
        self.assertIn("de", keys)
        self.assertIn("fr", keys)
        self.assertNotIn("us", keys)

    def test_custom_list_iso2(self):
        bone = _country_bone(values=["de", "at"])
        keys = list(bone.values.keys())
        self.assertIn("de", keys)
        self.assertIn("at", keys)
        self.assertNotIn("us", keys)

    def test_invalid_codes_raises(self):
        from viur.core.bones.selectcountry import SelectCountryBone
        with self.assertRaises(AssertionError):
            SelectCountryBone(codes=4)

    def test_values_sorted_by_name(self):
        bone = _country_bone(values=["de", "us", "at"])
        keys = list(bone.values.keys())
        # sorted by country name: Austria (at) < Germany (de) < United States (us)
        self.assertEqual(["at", "de", "us"], keys)


class TestSelectCountryBoneSingleValueUnserialize(ViURTestCase):

    def test_iso3_to_iso2_conversion(self):
        bone = _country_bone()  # ISO2 mode
        self.assertEqual("de", bone.singleValueUnserialize("deu"))

    def test_iso2_stays_iso2(self):
        bone = _country_bone()
        self.assertEqual("de", bone.singleValueUnserialize("de"))

    def test_iso2_to_iso3_conversion(self):
        from viur.core.bones.selectcountry import SelectCountryBone
        bone = _country_bone(codes=SelectCountryBone.ISO3)
        self.assertEqual("deu", bone.singleValueUnserialize("de"))

    def test_iso3_stays_iso3(self):
        from viur.core.bones.selectcountry import SelectCountryBone
        bone = _country_bone(codes=SelectCountryBone.ISO3)
        self.assertEqual("deu", bone.singleValueUnserialize("deu"))

    def test_unknown_iso3_returned_as_is(self):
        bone = _country_bone()
        self.assertEqual("xyz", bone.singleValueUnserialize("xyz"))

    def test_unknown_iso2_returned_as_is(self):
        from viur.core.bones.selectcountry import SelectCountryBone
        bone = _country_bone(codes=SelectCountryBone.ISO3)
        self.assertEqual("xx", bone.singleValueUnserialize("xx"))
