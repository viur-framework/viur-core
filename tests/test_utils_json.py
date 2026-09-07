"""Round-trip tests for viur.core.utils.json (ViURJsonEncoder, dumps, loads)."""
import datetime
import unittest
from decimal import Decimal

from viur.core.utils import json as viur_json


class TestViURJsonDecimal(unittest.TestCase):

    def test_decimal_roundtrip_is_exact(self):
        for raw in ("1234.56", "0", "-0.01", "1E+2", "12.500"):
            with self.subTest(raw=raw):
                back = viur_json.loads(viur_json.dumps({"amount": Decimal(raw)}))
                self.assertIsInstance(back["amount"], Decimal)
                self.assertEqual(back["amount"], Decimal(raw))

    def test_decimal_wire_format_is_marker_dict(self):
        self.assertEqual(viur_json.dumps(Decimal("1234.56")), '{".__decimal__": "1234.56"}')

    def test_decimal_inside_nested_structures(self):
        payload = {"lines": [{"total": Decimal("10.10")}, {"total": Decimal("0.90")}]}
        back = viur_json.loads(viur_json.dumps(payload))
        self.assertEqual(sum(line["total"] for line in back["lines"]), Decimal("11.00"))


class TestViURJsonExistingTypes(unittest.TestCase):

    def test_datetime_roundtrip(self):
        value = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(viur_json.loads(viur_json.dumps(value)), value)

    def test_timedelta_and_bytes_and_set_roundtrip(self):
        for value in (datetime.timedelta(seconds=5), b"x", {1, 2}):
            with self.subTest(value=value):
                self.assertEqual(viur_json.loads(viur_json.dumps(value)), value)

    def test_empty_and_zero_values_roundtrip(self):
        """Regression: the decoder used truthiness on the marker value, so timedelta(0),
        b"" and set() came back as the raw marker dict instead of the typed value."""
        for value in (datetime.timedelta(0), b"", set(), Decimal("0")):
            with self.subTest(value=value):
                back = viur_json.loads(viur_json.dumps(value))
                self.assertIs(type(back), type(value))
                self.assertEqual(back, value)

    def test_plain_dict_with_one_key_is_untouched(self):
        self.assertEqual(viur_json.loads('{"total": 0}'), {"total": 0})


class TestViURJsonDecimalSpecialValues(unittest.TestCase):

    def test_special_values_roundtrip(self):
        """str() is the exact wire form for every Decimal, including the non-finite ones and
        values a float would round or normalise (-0, exponent notation, 40 digits)."""
        for raw in ("-0", "0E-10", "1E-30", "Infinity", "-Infinity",
                    "123456789012345678901234567890.123456789"):
            with self.subTest(raw=raw):
                back = viur_json.loads(viur_json.dumps(Decimal(raw)))
                self.assertIsInstance(back, Decimal)
                self.assertEqual(str(back), str(Decimal(raw)))

    def test_nan_roundtrips_as_nan(self):
        for raw in ("NaN", "sNaN"):
            with self.subTest(raw=raw):
                back = viur_json.loads(viur_json.dumps(Decimal(raw)))
                self.assertTrue(back.is_nan())
                self.assertEqual(back.is_snan(), Decimal(raw).is_snan())

    def test_decode_does_not_round_to_context_precision(self):
        import decimal
        with decimal.localcontext() as ctx:
            ctx.prec = 3
            back = viur_json.loads(viur_json.dumps(Decimal("1.23456789")))
        self.assertEqual(back, Decimal("1.23456789"))
