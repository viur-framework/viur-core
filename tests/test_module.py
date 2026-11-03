import enum
import typing as t

from abstract import ViURTestCase


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class Number(enum.IntEnum):
    ONE = 1
    TWO = 2


SkelType = t.Literal["node", "leaf"]


class MethodTestCase(ViURTestCase):
    @staticmethod
    def _call(func: t.Callable, *args, **kwargs) -> t.Any:
        from viur.core.module import Method
        return Method(func)(*args, **kwargs)

    @staticmethod
    def _urlsafe_key(kind: str = "test", id_or_name: int | str = 4711) -> str:
        from viur.core import db
        return db.Key(kind, id_or_name).to_legacy_urlsafe().decode("ASCII")


class TestMethodScalarAnnotation(MethodTestCase):
    """Parsing of arguments annotated with a simple type."""

    def test_str(self):
        def func(value: str):
            return value

        self.assertEqual(self._call(func, "foo"), "foo")

    def test_int(self):
        def func(value: int):
            return value

        self.assertEqual(self._call(func, "42"), 42)
        self.assertEqual(self._call(func, value="42"), 42)

    def test_float(self):
        def func(value: float):
            return value

        self.assertEqual(self._call(func, "1.5"), 1.5)

    def test_bool(self):
        def func(value: bool):
            return value

        for truthy in ("1", "true", "yes", "True", " YES "):
            self.assertIs(self._call(func, truthy), True, truthy)
        for falsy in ("0", "false", "no", ""):
            self.assertIs(self._call(func, falsy), False, falsy)

    def test_invalid_keyword_value_is_not_acceptable(self):
        from viur.core import errors

        def func(value: int):
            return value

        with self.assertRaises(errors.NotAcceptable):
            self._call(func, value="foo")

    def test_unhandled_type_is_not_acceptable(self):
        from viur.core import errors

        def func(value: dict):
            return value

        with self.assertRaises(errors.NotAcceptable):
            self._call(func, "foo")


class TestMethodKeyAnnotation(MethodTestCase):
    """Parsing of arguments annotated with `db.Key` and the `db.KeyType` alias."""

    def test_key(self):
        from viur.core import db

        def func(value: db.Key):
            return value

        key = db.Key("test", 4711)
        self.assertEqual(self._call(func, self._urlsafe_key()), key)
        self.assertIs(self._call(func, key), key)

    def test_key_falls_back_to_int_and_str(self):
        from viur.core import db

        def func(value: db.Key):
            return value

        self.assertEqual(self._call(func, "42"), 42)
        self.assertEqual(self._call(func, "foo"), "foo")

    def test_key_type(self):
        from viur.core import db

        def func(value: db.KeyType):
            return value

        self.assertEqual(self._call(func, self._urlsafe_key()), db.Key("test", 4711))
        self.assertEqual(self._call(func, "42"), 42)
        self.assertEqual(self._call(func, "foo"), "foo")

    def test_optional_key(self):
        from viur.core import db

        def func(value: db.Key | int | str | None = None):
            return value

        self.assertIsNone(self._call(func))
        self.assertEqual(self._call(func, value=self._urlsafe_key()), db.Key("test", 4711))


class TestMethodLiteralAndEnumAnnotation(MethodTestCase):
    """Parsing of arguments annotated with a `Literal` or an `Enum`."""

    def test_literal(self):
        from viur.core import errors

        def func(value: t.Literal["de", "fr"]):
            return value

        self.assertEqual(self._call(func, "fr"), "fr")
        with self.assertRaises(errors.NotAcceptable):
            self._call(func, "en")

    def test_enum(self):
        from viur.core import errors

        def func(value: Color):
            return value

        self.assertIs(self._call(func, "blue"), Color.BLUE)
        with self.assertRaises(errors.NotAcceptable):
            self._call(func, "green")

    def test_int_enum_from_str(self):
        from viur.core import errors

        def func(value: Number):
            return value

        self.assertIs(self._call(func, "2"), Number.TWO)
        with self.assertRaises(errors.NotAcceptable):
            self._call(func, "3")


class TestMethodUnionAnnotation(MethodTestCase):
    """Parsing of arguments annotated with a union whose first member rejects the value."""

    def test_literal_member_falls_through(self):
        def func(value: t.Literal["node", "leaf"] | int | str):
            return value

        self.assertEqual(self._call(func, "node"), "node")
        self.assertEqual(self._call(func, "42"), 42)
        self.assertEqual(self._call(func, "foo"), "foo")
        self.assertEqual(self._call(func, value="foo"), "foo")

    def test_enum_member_falls_through(self):
        def func(value: Color | int):
            return value

        self.assertIs(self._call(func, "red"), Color.RED)
        self.assertEqual(self._call(func, "42"), 42)

    def test_literal_and_key_type(self):
        from viur.core import db

        def func(skel_type_or_key: SkelType | db.KeyType):
            return skel_type_or_key

        self.assertEqual(self._call(func, "leaf"), "leaf")
        self.assertEqual(self._call(func, self._urlsafe_key()), db.Key("test", 4711))
        self.assertEqual(self._call(func, "42"), 42)
        self.assertEqual(self._call(func, "foo"), "foo")

    def test_literal_and_key(self):
        from viur.core import db

        def func(value: t.Literal["SESSION"] | db.Key):
            return value

        self.assertEqual(self._call(func, "SESSION"), "SESSION")
        self.assertEqual(self._call(func, self._urlsafe_key()), db.Key("test", 4711))

    def test_optional_int(self):
        def func(value: t.Optional[int]):
            return value

        self.assertEqual(self._call(func, "42"), 42)
        self.assertIsNone(self._call(func, "None"))
        self.assertIsNone(self._call(func, "null"))

    def test_int_or_float(self):
        def func(value: int | float):
            return value

        self.assertEqual(self._call(func, "1"), 1)
        self.assertIsInstance(self._call(func, "1"), int)
        self.assertEqual(self._call(func, "1.5"), 1.5)

    def test_last_member_still_rejects(self):
        from viur.core import errors

        def func(value: int | t.Literal["node", "leaf"]):
            return value

        with self.assertRaises(errors.NotAcceptable):
            self._call(func, "foo")

    def test_no_member_matches_keyword_value(self):
        from viur.core import errors

        def func(value: Color | int):
            return value

        with self.assertRaises(errors.NotAcceptable):
            self._call(func, value="green")


class TestMethodContainerAnnotation(MethodTestCase):
    """Parsing of arguments annotated with `list` and `tuple`."""

    def test_list_wraps_single_value(self):
        def func(value: list[str]):
            return value

        self.assertEqual(self._call(func, "a"), ["a"])
        self.assertEqual(self._call(func, ["a", "b"]), ["a", "b"])

    def test_list_parses_items(self):
        def func(value: list[int]):
            return value

        self.assertEqual(self._call(func, ["1", "2"]), [1, 2])

    def test_list_of_enum(self):
        from viur.core import errors

        def func(value: list[Color]):
            return value

        self.assertEqual(self._call(func, ["red", "blue"]), [Color.RED, Color.BLUE])
        with self.assertRaises(errors.NotAcceptable):
            self._call(func, ["red", "green"])

    def test_tuple(self):
        def func(value: tuple[int]):
            return value

        self.assertEqual(self._call(func, "1"), (1,))
        self.assertEqual(self._call(func, ("1", "2")), (1, 2))


class TestMethodSignature(MethodTestCase):
    """Mapping of args and kwargs onto the signature."""

    def test_missing_required_parameter(self):
        from viur.core import errors

        def func(value: int):
            return value

        with self.assertRaises(errors.NotAcceptable):
            self._call(func)

    def test_default_is_kept(self):
        def func(value: int = 7):
            return value

        self.assertEqual(self._call(func), 7)

    def test_keyword_only(self):
        def func(*, value: int):
            return value

        self.assertEqual(self._call(func, value="42"), 42)

    def test_varargs_are_passed_unparsed(self):
        def func(first: int, *args):
            return first, args

        self.assertEqual(self._call(func, "1", "2", "3"), (1, ("2", "3")))

    def test_unknown_kwargs_are_dropped(self):
        def func(value: int):
            return value

        self.assertEqual(self._call(func, value="1", other="2"), 1)

    def test_varkwargs_are_passed_unparsed(self):
        def func(value: int, **kwargs):
            return value, kwargs

        self.assertEqual(self._call(func, value="1", other="2"), (1, {"other": "2"}))
