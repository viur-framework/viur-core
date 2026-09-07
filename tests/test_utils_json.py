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
