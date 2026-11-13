from abstract import ViURTestCase


class TestFromClientErrors(ViURTestCase):
    """fromClient drops harmless errors, but must keep the blocking ones (see #1544)."""

    def _record_skel(self):
        from viur.core.bones import RecordBone, StringBone
        from viur.core.skeleton import RelSkel

        class Rule(RelSkel):
            note = StringBone()
            day_type = StringBone(required=True)

        class Outer(RelSkel):
            rules = RecordBone(using=Rule, multiple=True, format="$(day_type)")

        return Outer()

    def test_record_row_without_required_field_is_rejected_with_an_error(self):
        skel = self._record_skel()

        complete = skel.fromClient({"rules.0.note": "x", "rules.0.day_type": ""})

        self.assertFalse(complete)
        self.assertIn(["rules", "0"], [error.fieldPath for error in skel.errors])

    def test_blocking_error_survives_a_harmless_one_after_it(self):
        from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
        from viur.core.skeleton import RelSkel

        class BlockingThenHarmless(BaseBone):
            def fromClient(self, skel, name, data):
                return [
                    ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Incomplete data"),
                    ReadFromClientError(ReadFromClientErrorSeverity.Empty, "Field not set", ["0", "day_type"]),
                ]

        class Probe(RelSkel):
            probe = BlockingThenHarmless()

        skel = Probe()

        self.assertFalse(skel.fromClient({"probe": "x"}))
        self.assertEqual([["probe"]], [error.fieldPath for error in skel.errors])

    def test_blocking_error_after_a_harmless_one_is_still_checked(self):
        from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
        from viur.core.skeleton import RelSkel

        class HarmlessThenBlocking(BaseBone):
            def fromClient(self, skel, name, data):
                return [
                    ReadFromClientError(ReadFromClientErrorSeverity.Empty, "Field not set", ["0", "day_type"]),
                    ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Broken"),
                ]

        class Probe(RelSkel):
            probe = HarmlessThenBlocking()

        skel = Probe()

        self.assertFalse(skel.fromClient({"probe": "x"}))
        self.assertEqual([["probe"]], [error.fieldPath for error in skel.errors])

    def test_harmless_errors_are_dropped(self):
        skel = self._record_skel()

        self.assertTrue(skel.fromClient({"rules.0.note": "x", "rules.0.day_type": "mon"}))
        self.assertEqual([], skel.errors)
