import functools
from unittest import mock

from abstract import ViURTestCase


class TestRecordBonePerformMagic(ViURTestCase):
    """``RecordBone.performMagic`` must forward to the sub-bones of every record value."""

    def setUp(self) -> None:
        super().setUp()
        from viur.core.bones import BaseBone, DateBone, StringBone
        from viur.core.skeleton import RelSkel

        class MagicBone(BaseBone):
            def performMagic(self, valuesCache, name, isAdd):
                valuesCache[name] = "added" if isAdd else "edited"

        def _strip(bone, skel, name, isAdd):
            skel[name] = (skel[name] or "").strip("/")

        url = StringBone()
        url.performMagic = functools.partial(_strip, url)  # magic set on the instance

        class MagicSkel(RelSkel):
            name = StringBone()
            magic = MagicBone()
            changed = DateBone(updateMagic=True)

        MagicSkel.url = url
        MagicSkel.__boneMap__["url"] = url

        class PlainSkel(RelSkel):
            name = StringBone()

        self.MagicSkel = MagicSkel
        self.PlainSkel = PlainSkel

    def _bone(self, using, **kwargs):
        from viur.core.bones import RecordBone

        return RecordBone(using=using, format="$(name)", **kwargs)

    def _value(self, using, **values):
        value = using()
        for name, val in values.items():
            value[name] = val
        return value

    def test_multiple(self):
        values = [self._value(self.MagicSkel, url="/a/"), self._value(self.MagicSkel, url="/b/")]

        self._bone(self.MagicSkel, multiple=True).performMagic({"rec": values}, "rec", isAdd=True)

        self.assertEqual(["added", "added"], [value["magic"] for value in values])
        self.assertEqual(["a", "b"], [value["url"] for value in values])
        self.assertTrue(all(value["changed"] for value in values))

    def test_is_add_is_passed(self):
        value = self._value(self.MagicSkel, name="x")  # an empty record value is falsy and skipped

        self._bone(self.MagicSkel).performMagic({"rec": value}, "rec", isAdd=False)

        self.assertEqual("edited", value["magic"])

    def test_languages(self):
        value = self._value(self.MagicSkel)

        self._bone(self.MagicSkel, languages=["de", "en"]).performMagic(
            {"rec": {"de": value, "en": None}}, "rec", isAdd=True,
        )

        self.assertEqual("added", value["magic"])

    def test_none_value_is_skipped(self):
        value = self._value(self.MagicSkel)

        self._bone(self.MagicSkel, multiple=True).performMagic({"rec": [None, value]}, "rec", isAdd=True)

        self.assertEqual("added", value["magic"])

    def test_value_not_loaded_without_magic(self):
        """Records without any magic sub-bone must not be unserialized on every write."""
        skel = mock.MagicMock()

        self._bone(self.PlainSkel, multiple=True).performMagic(skel, "rec", isAdd=True)

        skel.__getitem__.assert_not_called()
