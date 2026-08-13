import string
import typing as t
from viur.core import i18n
from .base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity


class ColorBone(BaseBone):
    r"""
    ColorBone is a custom bone class for storing color values in the ViUR framework.
    It inherits from the BaseBone class in the viur.core.bones.base module.

    :param type: A string representing the bone type, set to "color".
    :param mode: A string specifying the color mode, either "rgb" or "rgba". Default is "rgb".
    :param \**kwargs: Additional keyword arguments passed to the BaseBone constructor.
    """
    type = "color"

    # Accepted number of hex digits (without the leading "#") per mode
    VALID_LENGTHS: t.Final[dict[str, tuple[int, ...]]] = {
        "rgb": (3, 6),
        "rgba": (8,),
    }

    def __init__(self, *, mode="rgb", **kwargs):  # mode rgb/rgba
        super().__init__(**kwargs)
        assert mode in self.VALID_LENGTHS
        self.mode = mode

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        """
        Normalize a hex color to a lower-case value with exactly one leading "#".

        A leading "#" is optional in the input, but it's the only position a "#" may
        appear in. The remaining characters must be hex digits in a length valid for
        the bone's mode; the 3-digit shorthand is expanded. Everything else is
        rejected as invalid.
        """
        def invalid():
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid)]

        if not isinstance(value, str):
            return invalid()

        value = value.lower()

        if value.startswith("#"):  # strip the optional leading "#"
            value = value[1:]

        if any(char not in string.hexdigits for char in value):
            return invalid()

        if len(value) not in self.VALID_LENGTHS[self.mode]:
            return invalid()

        if len(value) == 3:  # expand the shorthand: "abc" --> "aabbcc"
            value = "".join(char * 2 for char in value)

        value = f"#{value}"

        err = self.isInvalid(value)
        if not err:
            return value, None

        return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

    def structure(self) -> dict:
        return super().structure() | {
            "mode": self.mode,
        }
