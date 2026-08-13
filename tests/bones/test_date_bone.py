from datetime import datetime as dt, timedelta as td, timezone as tz

from abstract import ViURTestCase


class TestDateBone(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "myDateBone"

    def test_isEmpty_default_bone(self):
        from viur.core.bones import DateBone
        self._run_tests(bone := DateBone(descr="empty_datebone"))
        self.assertEqual(None, bone.getEmptyValue())
        self.assertIsNone(bone.defaultValue)

    def _run_tests(self, bone):
        self.assertTrue(bone.isEmpty(""))
        self.assertTrue(bone.isEmpty(None))
        self.assertTrue(bone.isEmpty([]))
        self.assertTrue(bone.isEmpty(bone.getEmptyValue()))


class TestDateBone_setBoneValue(ViURTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "myDateBone"

    def test_setBoneValue_single(self):
        from viur.core.bones import DateBone
        # now
        bone = DateBone()
        skel = {}
        self.assertTrue(bone.setBoneValue(skel, self.bone_name, "now", False, None))
        self.assertIn(self.bone_name, skel)
        self.assertIsInstance(skel[self.bone_name], dt)
        self.assertGreaterEqual(skel[self.bone_name], dt.now(tz=tz.utc) - td(minutes=1))
        self.assertLessEqual(skel[self.bone_name], dt.now(tz=tz.utc))

        # now-3600
        bone = DateBone()
        skel = {}
        self.assertTrue(bone.setBoneValue(skel, self.bone_name, "now-3600", False, None))
        self.assertIn(self.bone_name, skel)
        self.assertIsInstance(skel[self.bone_name], dt)
        self.assertGreaterEqual(skel[self.bone_name], dt.now(tz=tz.utc) - td(minutes=1, hours=1))
        self.assertLessEqual(skel[self.bone_name], dt.now(tz=tz.utc) - td(hours=1))

        # now-foo (invalid)
        bone = DateBone()
        skel = {}
        self.assertFalse(bone.setBoneValue(skel, self.bone_name, "now-foo", False, None))
        self.assertNotIn(self.bone_name, skel)

        self._check_against_fmts(
            dt(2000, 1, 1, 10, 20, 30, tzinfo=tz.utc), (
                "%Y-%m-%d %H:%M:%S",
                "%m/%d/%Y %H:%M:%S",
                "%d.%m.%Y %H:%M:%S",
            )
        )

        self._check_against_fmts(
            dt(2000, 1, 1, 10, 20, tzinfo=tz.utc), (
                "%Y-%m-%d %H:%M",
                "%m/%d/%Y %H:%M",
                "%d.%m.%Y %H:%M",
            )
        )

        self._check_against_fmts(
            dt(2000, 1, 1, tzinfo=tz.utc), (
                "%Y-%m-%d",
                "%m/%d/%Y",
                "%d.%m.%Y",
            )
        )

    def _check_against_fmts(self, value: dt, fmts: tuple[str, ...]) -> None:
        from viur.core.bones import DateBone

        for fmt in fmts:
            print(f"Check {fmt = } with {value = }")
            bone = DateBone()
            skel = {}
            self.assertTrue(bone.setBoneValue(skel, self.bone_name, value.strftime(fmt), False, None))
            self.assertIn(self.bone_name, skel)
            self.assertEqual(skel[self.bone_name], value)


class TestDateBone_now(ViURTestCase):
    """Tests for the "now" / "nowX" input format, which is accepted by any bone carrying a time."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bone_name = "myDateBone"

    def _assert_now(self, bone, value: str, offset: td = td()) -> None:
        """Assert that `value` is accepted and resolves to the current time plus `offset`."""
        skel = {}
        before = dt.now(tz=tz.utc)
        self.assertTrue(bone.setBoneValue(skel, self.bone_name, value, False, None))
        after = dt.now(tz=tz.utc)

        self.assertIn(self.bone_name, skel)
        result = skel[self.bone_name]
        self.assertIsInstance(result, dt)
        # microseconds are stripped, so the result may lag up to one second behind
        self.assertGreaterEqual(result, before + offset - td(seconds=1))
        self.assertLessEqual(result, after + offset)

    def _assert_invalid(self, bone, value: str) -> None:
        skel = {}
        self.assertFalse(bone.setBoneValue(skel, self.bone_name, value, False, None))
        self.assertNotIn(self.bone_name, skel)

    def test_now_date_and_time(self):
        from viur.core.bones import DateBone
        self._assert_now(DateBone(), "now")

    def test_now_time_only(self):
        from viur.core.bones import DateBone
        self._assert_now(DateBone(date=False), "now")

    def test_now_rejected_on_date_only(self):
        from viur.core.bones import DateBone
        # without a time there is nothing "now" could express, the date part is cropped anyway
        self._assert_invalid(DateBone(time=False), "now")
        self._assert_invalid(DateBone(time=False), "now5")

    def test_now_case_insensitive(self):
        from viur.core.bones import DateBone
        self._assert_now(DateBone(), "NOW")
        self._assert_now(DateBone(), "Now")
        self._assert_now(DateBone(), "NOW5", td(seconds=5))

    def test_now_offset(self):
        from viur.core.bones import DateBone
        # a single-digit offset must not be swallowed
        self._assert_now(DateBone(), "now5", td(seconds=5))
        self._assert_now(DateBone(), "now10", td(seconds=10))
        self._assert_now(DateBone(), "now-5", td(seconds=-5))
        self._assert_now(DateBone(), "now-3600", td(hours=-1))

    def test_now_offset_time_only(self):
        from viur.core.bones import DateBone
        self._assert_now(DateBone(date=False), "now5", td(seconds=5))

    def test_now_invalid_offset(self):
        from viur.core.bones import DateBone
        self._assert_invalid(DateBone(), "nowfoo")
        self._assert_invalid(DateBone(), "now-foo")
        self._assert_invalid(DateBone(date=False), "nowfoo")
