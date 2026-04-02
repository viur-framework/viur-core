import enum

from abstract import ViURTestCase


class Color(enum.Enum):
    red = "red"
    green = "green"
    blue = "blue"


# SelectBone.values calls translate() with self.skel_cls.__name__ in the hint.
# Outside a real Skeleton this is None, so we wire up a stub class and name.
_DummySkel = type("DummySkel", (), {})


def _select_bone(**kwargs):
    from viur.core.bones.select import SelectBone
    bone = SelectBone(**kwargs)
    bone.skel_cls = _DummySkel
    bone.name = "testbone"
    return bone


class TestSelectBoneValues(ViURTestCase):
    """SelectBone: values resolution from dict, list, callable, and Enum."""

    def test_dict_values(self):
        bone = _select_bone(values={"a": "Alpha", "b": "Beta"})
        self.assertIn("a", bone.values)
        self.assertIn("b", bone.values)

    def test_list_values_converted_to_dict(self):
        bone = _select_bone(values=["x", "y", "z"])
        self.assertIn("x", bone.values)
        self.assertIn("y", bone.values)

    def test_callable_values(self):
        bone = _select_bone(values=lambda: {"a": "Alpha"})
        self.assertIn("a", bone.values)

    def test_enum_values(self):
        bone = _select_bone(values=Color)
        # enum values should be keyed by .value
        self.assertIn("red", bone.values)
        self.assertIn("green", bone.values)

    def test_empty_values(self):
        bone = _select_bone(values={})
        self.assertEqual({}, bone.values)


class TestSelectBoneSingleValueFromClient(ViURTestCase):
    """SelectBone.singleValueFromClient: valid selection, empty, and invalid."""

    def _from_client(self, bone, value):
        return bone.singleValueFromClient(value, {}, "status", {})

    def test_valid_string_key(self):
        bone = _select_bone(values={"active": "Active", "inactive": "Inactive"})
        val, err = self._from_client(bone, "active")
        self.assertIsNone(err)
        self.assertEqual("active", val)

    def test_valid_numeric_key(self):
        bone = _select_bone(values={1: "One", 2: "Two"})
        val, err = self._from_client(bone, "1")
        self.assertIsNone(err)
        self.assertEqual(1, val)

    def test_empty_value_returns_error(self):
        bone = _select_bone(values={"a": "Alpha"})
        val, err = self._from_client(bone, "")
        self.assertIsNotNone(err)

    def test_invalid_value_returns_error(self):
        bone = _select_bone(values={"a": "Alpha", "b": "Beta"})
        val, err = self._from_client(bone, "c")
        self.assertIsNotNone(err)

    def test_enum_value_passthrough(self):
        bone = _select_bone(values=Color)
        # passing an enum instance directly skips string matching
        val, err = self._from_client(bone, Color.red)
        self.assertIsNone(err)
        self.assertEqual(Color.red, val)

    def test_enum_string_resolves_to_enum(self):
        bone = _select_bone(values=Color)
        val, err = self._from_client(bone, "red")
        self.assertIsNone(err)
        self.assertEqual(Color.red, val)


class TestSelectBoneAtomicDump(ViURTestCase):
    """SelectBone._atomic_dump: enum serialization."""

    def test_enum_dumps_to_value(self):
        bone = _select_bone(values=Color)
        self.assertEqual("red", bone._atomic_dump(Color.red))

    def test_non_enum_passthrough(self):
        bone = _select_bone(values={"a": "Alpha"})
        self.assertEqual("a", bone._atomic_dump("a"))
        self.assertEqual(42, bone._atomic_dump(42))
