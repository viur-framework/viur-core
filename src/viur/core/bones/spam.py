import logging
import random
import typing as t
from viur.core import i18n, current
from viur.core.bones import NumericBone
from viur.core.bones.base import getSystemInitialized


class SpamBone(NumericBone):
    type = "numeric.spam"

    def __init__(
        self,
        descr: str = i18n.translate(
            "core.bones.spam.question",
            "What is the result of the addition of {{a}} and {{b}}?"
        ),
        values: t.Iterable[str] = tuple(
            i18n.translate(f"core.bones.spam.value.{digit}", digit)
            for digit in ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
        ),
        required: bool = True,
        msg_invalid: str = i18n.translate(
            "core.bones.spam.invalid",
            "Your answer was wrong! Please try again."
        ),
        **kwargs
    ):
        if "precision" in kwargs:
            raise ValueError(f"Cannot use {self.__class__.__name__!r} with a precision")

        super().__init__(
            required=required,
            precision=0,
            **kwargs
        )

        self.values = tuple(values)
        if not self.values or len(self.values) == 1:
            raise ValueError("Requires for at least 2 values!")

        self.descr_template = descr
        self.msg_invalid = msg_invalid

    def _dice(self) -> int:
        return random.randint(1, len(self.values))

    @property
    def descr(self):
        """
        The descr-property is generated and uses session variables to construct the question.
        """
        # This descr can only be evaluated on initialized systems.
        if not getSystemInitialized():
            return None

        session = current.session.get()

        a = session.get("spambone.value.a")
        b = session.get("spambone.value.b")

        if a is None or b is None:
            a = session["spambone.value.a"] = self._dice()
            b = session["spambone.value.b"] = self._dice()

        return i18n.translate(self.descr_template).translate(a=self.values[a - 1], b=self.values[b - 1])

    @descr.setter
    def descr(self, value: t.Any) -> None:
        """
        This setter is a null operation. It makes it possible to make a
        super call in init, although the `descr` attribute is set there.
        """
        pass

    def isInvalid(self, value):
        session = current.session.get()

        a = session.get("spambone.value.a") or 0
        b = session.get("spambone.value.b") or 0

        if a and b:
            del session["spambone.value.a"]
            del session["spambone.value.b"]

            try:
                value = int(value)
            except ValueError:
                value = 0

        logging.debug(f"{a=}, {b=}, {value=}, expecting {a + b=}")
        if value != a + b:
            return str(self.msg_invalid)
