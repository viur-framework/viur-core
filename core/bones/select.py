import enum
from collections import OrderedDict
from numbers import Number
from typing import Callable, Dict, List, Tuple, Union

from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.i18n import translate

SelectBoneValue = Union[str, Number, enum.Enum]
"""
Type alias of possible values in a SelectBone. SelectBoneValue can be either a string (str) or a number (Number)
"""

SelectBoneMultiple = List[SelectBoneValue]
""" SelectBoneMultiple is a list of SelectBoneValue elements."""


class SelectBone(BaseBone):
    """
    A SelectBone is a bone which can take a value from a certain list of values..
    Inherits from the BaseBone class. The `type` attribute is set to "select".

    :param defaultValue: key(s) of the values which will be checked by default.
    :param values: dict of key->value pairs from which the user can choose from.
    :param kwargs: Additional keyword arguments that will be passed to the superclass' __init__ method.
    """
    type = "select"

    def __init__(
        self,
        *,
        defaultValue: Union[
            SelectBoneValue,
            SelectBoneMultiple,
            Dict[str, Union[SelectBoneMultiple, SelectBoneValue]],
        ] = None,
        values: Union[Dict, List, Tuple, Callable, enum.EnumMeta] = (),
        **kwargs
    ):

        super().__init__(defaultValue=defaultValue, **kwargs)

        # handle list/tuple as dicts
        if isinstance(values, (list, tuple)):
            values = {i: translate(i) for i in values}

        assert isinstance(values, (dict, OrderedDict)) or callable(values)
        self._values = values

    def __getattribute__(self, item):
        """
        Overrides the default __getattribute__ method to handle the 'values' attribute dynamically. If the '_values'
        attribute is callable, it will be called and the result will be stored in the 'values' attribute.

        :param str item: The attribute name.
        :return: The value of the specified attribute.

        :raises AssertionError: If the resulting values are not of type dict or OrderedDict.
        """
        if item == "values":
            values = self._values
            if isinstance(values, enum.EnumMeta):
                values = {value.value: translate(value.name) for value in values}
            elif callable(values):
                values = values()

                # handle list/tuple as dicts
                if isinstance(values, (list, tuple)):
                    values = {i: translate(i) for i in values}

                assert isinstance(values, (dict, OrderedDict))

            return values

        return super().__getattribute__(item)

    def singleValueUnserialize(self, val):
        if isinstance(self._values, enum.EnumMeta):
            for value in self._values:
                if value.value == val:
                    return value
        return val

    def singleValueSerialize(self, val, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        if isinstance(self._values, enum.EnumMeta) and isinstance(val, self._values):
            return val.value
        return val

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        if not str(value):
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Empty, "No value selected")]
        for key in self.values.keys():
            if str(key) == str(value):
                if isinstance(self._values, enum.EnumMeta):
                    return self._values(key), None
                return key, None
        return self.getEmptyValue(), [
            ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid value selected")]

    def structure(self) -> dict:
        return super().structure() | {
            "values": [(k, str(v)) for k, v in self.values.items()],
        }
