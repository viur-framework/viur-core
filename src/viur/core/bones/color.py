import string
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity


class ColorBone(BaseBone):
    r"""
    ColorBone is a custom bone class for storing color values in the ViUR framework.
    It inherits from the BaseBone class in the viur.core.bones.base module.

    :param type: A string representing the bone type, set to "color".
    :param mode: A string specifying the color mode, either "rgb" or "rgba". Default is "rgb".
    :param \**kwargs: Additional keyword arguments passed to the BaseBone constructor.
    """
    type = "color"

    def __init__(self, *, mode="rgb", **kwargs):  # mode rgb/rgba
        super().__init__(**kwargs)
        assert mode in {"rgb", "rgba"}
        self.mode = mode

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        value = value.lower()
        if value.count("#") > 1:
            return self.getEmptyValue(), [
                ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")]
        for char in value:
            if char not in string.hexdigits + "#":
                return self.getEmptyValue(), [
                    ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")]
        if self.mode == "rgb":
            if len(value) == 3:
                value = "#" + value
            if len(value) == 4:
                value = value[0:2] + value[1] + 2 * value[2] + 2 * value[3]
            if len(value) == 6 or len(value) == 7:
                if len(value) == 6:
                    value = "#" + value
            else:
                return self.getEmptyValue(), [
                    ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")]
        if self.mode == "rgba":
            if len(value) == 8 or len(value) == 9:
                if len(value) == 8:
                    value = "#" + value
            else:
                return self.getEmptyValue(), [
                    ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")]
        err = self.isInvalid(value)
        if not err:
            return value, None
        return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
