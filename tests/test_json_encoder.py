"""Tests for CustomJsonEncoder Decimal support.

Loads default.py in isolation by patching sys.modules during the importlib call
so the skeleton path-validation never runs. Stubs are automatically reverted
by mock.patch.dict, keeping sys.modules clean for other test files.
"""
import importlib.util
import json
import pathlib
import sys
import types
import unittest
import warnings
from decimal import Decimal
from unittest import mock

_RENDER_JSON_DEFAULT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src/viur/core/render/json/default.py"
)


def _load_custom_json_encoder():
    """Load CustomJsonEncoder without executing viur.core.__init__ chain.

    default.py's top-level imports are:
        from viur.core import db, current
        from viur.core.bones import BaseBone
        from viur.core.render.abstract import AbstractRenderer
        from viur.core.skeleton import SkeletonInstance, SkelList
        from viur.core.i18n import translate
        from viur.core.config import conf
        from deprecated.sphinx import deprecated

    We stub every module in that list so no transitive imports happen.
    """

    class _Key:
        pass

    class _BaseBone:
        pass

    class _AbstractRenderer:
        pass

    class _SkeletonInstance:
        pass

    class _SkelList(list):
        pass

    class _translate(str):
        pass

    class _conf_obj:
        compatibility: set = set()

    def _noop_deprecated(**kw):
        return lambda fn: fn

    def _pkg(name, **attrs):
        m = types.ModuleType(name)
        m.__path__ = []
        m.__package__ = name
        for k, v in attrs.items():
            setattr(m, k, v)
        return m

    # Build stubs for every module default.py depends on.
    # Prefer the real module when it's already in sys.modules, but
    # DO stub viur.core itself to prevent __init__ from running.
    _current_stub = _pkg("viur.core.current")
    _db_stub = _pkg("viur.core.db", Key=_Key)

    # viur.core package stub — must expose db and current as attributes
    # so that `from viur.core import db, current` works without __init__
    _core_stub = _pkg("viur.core", db=_db_stub, current=_current_stub)

    patch = {
        "viur.core": _core_stub,
        "viur.core.db": _db_stub,
        "viur.core.current": _current_stub,
        "viur.core.bones": _pkg("viur.core.bones", BaseBone=_BaseBone),
        "viur.core.render": _pkg("viur.core.render"),
        "viur.core.render.abstract": _pkg(
            "viur.core.render.abstract", AbstractRenderer=_AbstractRenderer
        ),
        "viur.core.render.json": _pkg("viur.core.render.json"),
        "viur.core.skeleton": _pkg(
            "viur.core.skeleton",
            SkeletonInstance=_SkeletonInstance,
            SkelList=_SkelList,
        ),
        "viur.core.i18n": _pkg("viur.core.i18n", translate=_translate),
        "viur.core.config": _pkg("viur.core.config", conf=_conf_obj()),
        "deprecated": _pkg("deprecated"),
        "deprecated.sphinx": _pkg("deprecated.sphinx", deprecated=_noop_deprecated),
        # Clear any prior load of default.py so the body re-runs
        "viur.core.render.json.default": None,
    }

    with mock.patch.dict(sys.modules, patch):
        _spec = importlib.util.spec_from_file_location(
            "viur.core.render.json.default",
            str(_RENDER_JSON_DEFAULT),
        )
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["viur.core.render.json.default"] = _mod
        _spec.loader.exec_module(_mod)
        # Grab conf reference while the patch is still active so the module
        # object's own `conf` attribute (used in default()) points to our stub
        _mod_conf_stub = sys.modules["viur.core.config"].conf

    # Re-register the loaded module so mock.patch.object() works in tests
    sys.modules["viur.core.render.json.default"] = _mod
    return _mod, _mod_conf_stub


_default_mod, _conf_stub = _load_custom_json_encoder()
CustomJsonEncoder = _default_mod.CustomJsonEncoder


class TestCustomJsonEncoder_Decimal(unittest.TestCase):

    def test_decimal_default_returns_float(self):
        result = json.loads(json.dumps({"amount": Decimal("1234.56")}, cls=CustomJsonEncoder))
        self.assertIsInstance(result["amount"], float)
        self.assertAlmostEqual(result["amount"], 1234.56)

    def test_decimal_compat_flag_returns_string(self):
        with mock.patch.object(_default_mod, "conf") as mock_conf:
            mock_conf.compatibility = {"json.decimal.as_string"}
            result = json.loads(json.dumps({"amount": Decimal("1234.56")}, cls=CustomJsonEncoder))
            self.assertIsInstance(result["amount"], str)
            self.assertEqual(result["amount"], "1234.56")

    def test_decimal_default_emits_deprecation_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            json.dumps({"amount": Decimal("1234.56")}, cls=CustomJsonEncoder)
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            self.assertTrue(len(deprecation_warnings) >= 1)
            self.assertIn("json.decimal.as_string", str(deprecation_warnings[0].message))

    def test_decimal_compat_flag_no_warning(self):
        with mock.patch.object(_default_mod, "conf") as mock_conf:
            mock_conf.compatibility = {"json.decimal.as_string"}
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                json.dumps({"amount": Decimal("1234.56")}, cls=CustomJsonEncoder)
                deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
                self.assertEqual(len(deprecation_warnings), 0)

    def test_existing_types_unchanged(self):
        from datetime import datetime
        from enum import Enum

        class Color(Enum):
            RED = "red"

        result = json.loads(json.dumps({
            "dt": datetime(2026, 1, 1, 12, 0),
            "enum": Color.RED,
            "set": {1, 2, 3},
        }, cls=CustomJsonEncoder))

        self.assertEqual(result["dt"], "2026-01-01T12:00:00")
        self.assertEqual(result["enum"], "red")
        self.assertIsInstance(result["set"], list)
