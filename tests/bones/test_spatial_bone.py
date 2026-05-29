from abstract import ViURTestCase

# Germany bounding box used throughout
BOUNDS_LAT = (47.0, 55.0)
BOUNDS_LNG = (6.0, 15.0)
GRID = (10, 10)


def _bone(**kwargs):
    from viur.core.bones.spatial import SpatialBone
    return SpatialBone(boundsLat=BOUNDS_LAT, boundsLng=BOUNDS_LNG, gridDimensions=GRID, **kwargs)


class TestHaversine(ViURTestCase):

    def test_same_point_is_zero(self):
        from viur.core.bones.spatial import haversine
        self.assertAlmostEqual(0.0, haversine(52.5, 13.4, 52.5, 13.4), places=1)

    def test_munich_berlin_approx_500km(self):
        from viur.core.bones.spatial import haversine
        # Munich (48.14, 11.58) to Berlin (52.52, 13.40) ≈ 504 km
        dist = haversine(48.14, 11.58, 52.52, 13.40)
        self.assertAlmostEqual(504_000, dist, delta=5000)

    def test_equator_longitude_diff(self):
        from viur.core.bones.spatial import haversine
        # 1° longitude on equator ≈ 111 km
        dist = haversine(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(111_000, dist, delta=1000)

    def test_symmetry(self):
        from viur.core.bones.spatial import haversine
        d1 = haversine(48.0, 11.0, 52.0, 13.0)
        d2 = haversine(52.0, 13.0, 48.0, 11.0)
        self.assertAlmostEqual(d1, d2, places=3)


class TestSpatialBoneInit(ViURTestCase):

    def test_valid_init(self):
        bone = _bone()
        self.assertEqual(BOUNDS_LAT, bone.boundsLat)
        self.assertEqual(BOUNDS_LNG, bone.boundsLng)
        self.assertEqual(GRID, bone.gridDimensions)

    def test_invalid_lat_too_low(self):
        from viur.core.bones.spatial import SpatialBone
        with self.assertRaises(ValueError):
            SpatialBone(boundsLat=(-91.0, 55.0), boundsLng=BOUNDS_LNG, gridDimensions=GRID)

    def test_invalid_lat_too_high(self):
        from viur.core.bones.spatial import SpatialBone
        with self.assertRaises(ValueError):
            SpatialBone(boundsLat=(47.0, 91.0), boundsLng=BOUNDS_LNG, gridDimensions=GRID)

    def test_invalid_lng_too_low(self):
        from viur.core.bones.spatial import SpatialBone
        with self.assertRaises(ValueError):
            SpatialBone(boundsLat=BOUNDS_LAT, boundsLng=(-181.0, 15.0), gridDimensions=GRID)

    def test_invalid_lng_too_high(self):
        from viur.core.bones.spatial import SpatialBone
        with self.assertRaises(ValueError):
            SpatialBone(boundsLat=BOUNDS_LAT, boundsLng=(6.0, 181.0), gridDimensions=GRID)

    def test_boundsLat_wrong_type_raises(self):
        from viur.core.bones.spatial import SpatialBone
        with self.assertRaises(AssertionError):
            SpatialBone(boundsLat=[47.0, 55.0], boundsLng=BOUNDS_LNG, gridDimensions=GRID)


class TestSpatialBoneGetGridSize(ViURTestCase):

    def test_grid_size(self):
        bone = _bone()
        lat_size, lng_size = bone.getGridSize()
        self.assertAlmostEqual((55.0 - 47.0) / 10.0, lat_size)
        self.assertAlmostEqual((15.0 - 6.0) / 10.0, lng_size)


class TestSpatialBoneIsInvalid(ViURTestCase):

    def setUp(self):
        super().setUp()
        self.bone = _bone()

    def test_valid_point(self):
        self.assertFalse(self.bone.isInvalid((51.0, 10.0)))  # inside Germany

    def test_lat_too_low(self):
        result = self.bone.isInvalid((46.0, 10.0))  # lat < 47
        self.assertTrue(result)

    def test_lat_too_high(self):
        result = self.bone.isInvalid((56.0, 10.0))
        self.assertTrue(result)

    def test_lng_too_low(self):
        result = self.bone.isInvalid((51.0, 5.0))
        self.assertTrue(result)

    def test_lng_too_high(self):
        result = self.bone.isInvalid((51.0, 16.0))
        self.assertTrue(result)

    def test_boundary_lat_min(self):
        self.assertFalse(self.bone.isInvalid((47.0, 10.0)))

    def test_boundary_lat_max(self):
        self.assertFalse(self.bone.isInvalid((55.0, 10.0)))

    def test_invalid_value_type(self):
        result = self.bone.isInvalid("not-a-tuple")
        self.assertTrue(result)


class TestSpatialBoneIsEmpty(ViURTestCase):

    def setUp(self):
        super().setUp()
        self.bone = _bone()

    def test_empty_tuple_is_empty(self):
        self.assertTrue(self.bone.isEmpty(()))

    def test_none_is_empty(self):
        self.assertTrue(self.bone.isEmpty(None))

    def test_empty_value_is_empty(self):
        self.assertTrue(self.bone.isEmpty(self.bone.getEmptyValue()))

    def test_valid_coord_not_empty(self):
        self.assertFalse(self.bone.isEmpty((51.0, 10.0)))

    def test_dict_form_is_empty_when_zero(self):
        self.assertTrue(self.bone.isEmpty({"lat": 0.0, "lng": 0.0}))

    def test_dict_form_not_empty(self):
        self.assertFalse(self.bone.isEmpty({"lat": 51.0, "lng": 10.0}))


class TestSpatialBoneSingleValueFromClient(ViURTestCase):

    def setUp(self):
        super().setUp()
        self.bone = _bone()

    def _from_client(self, value):
        return self.bone.singleValueFromClient(value, {}, "location", {})

    def test_valid_coordinates(self):
        val, err = self._from_client({"lat": 51.0, "lng": 10.0})
        self.assertIsNone(err)
        self.assertEqual((51.0, 10.0), val)

    def test_string_coordinates_parsed(self):
        val, err = self._from_client({"lat": "51.5", "lng": "10.2"})
        self.assertIsNone(err)
        self.assertAlmostEqual(51.5, val[0])

    def test_missing_both_returns_notset(self):
        from viur.core.bones.base import ReadFromClientErrorSeverity
        val, err = self._from_client({})
        self.assertIsNotNone(err)
        self.assertEqual(ReadFromClientErrorSeverity.NotSet, err[0].severity)

    def test_missing_lng_returns_empty(self):
        from viur.core.bones.base import ReadFromClientErrorSeverity
        val, err = self._from_client({"lat": 51.0})
        self.assertIsNotNone(err)
        self.assertEqual(ReadFromClientErrorSeverity.Empty, err[0].severity)

    def test_out_of_bounds_returns_error(self):
        val, err = self._from_client({"lat": 10.0, "lng": 10.0})  # lat < 47
        self.assertIsNotNone(err)


class TestSpatialBoneSingleValueUnserialize(ViURTestCase):

    def setUp(self):
        super().setUp()
        self.bone = _bone()

    def test_deserialize(self):
        val = self.bone.singleValueUnserialize({"coordinates": {"lat": 51.0, "lng": 10.0}})
        self.assertEqual((51.0, 10.0), val)

    def test_falsy_returns_none(self):
        self.assertIsNone(self.bone.singleValueUnserialize(None))
        self.assertIsNone(self.bone.singleValueUnserialize({}))
