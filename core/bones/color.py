"""
The class ColorBone is used to store color values. It inherits from the BaseBone class.
"""
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from typing import List, Union
import logging


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

    def singleValueFromClient(self, value, skel: 'viur.core.skeleton.SkeletonInstance', name: str, origData):
        """
        Processes a single value from the client, ensuring it is a valid color value,
        and returns a tuple containing the processed value and any errors that occurred.

        :param value: The value to be processed.
        :param skel: The skeleton instance associated with the value.
        :param name: The name of the bone.
        :param origData: The original data for the bone.

        :return tuple: A tuple containing the processed value if valid,
            or the empty value if invalid, and a list of ReadFromClientError instances
            if there were errors, or None if no errors occurred.
        """
        value = value.lower()
        if value.count("#") > 1:
            return self.getEmptyValue(), [
                ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value entered")]
        for char in value:
            if not char in "#0123456789abcdef":
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
