import enum
import typing as t

from abstract import ViURTestCase


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class TestMethodUnionAnnotation(ViURTestCase):
    """Parsing of arguments annotated with a union whose first member rejects the value."""

    @staticmethod
    def _call(func: t.Callable, *args, **kwargs) -> t.Any:
        from viur.core.module import Method
        return Method(func)(*args, **kwargs)

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

    def test_last_member_still_rejects(self):
        from viur.core import errors

        def func(value: int | t.Literal["node", "leaf"]):
            return value

        with self.assertRaises(errors.NotAcceptable):
            self._call(func, "foo")
