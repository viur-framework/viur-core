import unittest
from datetime import datetime as dt, timedelta as td, timezone as tz


class TestDateBone(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from main import monkey_patch
        monkey_patch()
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


class TestDateBone_setBoneValue(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from main import monkey_patch
        monkey_patch()
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
            self.assertEquals(skel[self.bone_name], value)
