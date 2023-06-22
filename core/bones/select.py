import enum
from collections import OrderedDict
from numbers import Number
from typing import Callable, Dict, List, Tuple, Union

from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.i18n import translate

SelectBoneValue = Union[str, Number, enum.Enum]
SelectBoneMultiple = List[SelectBoneValue]


class SelectBone(BaseBone):
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
        """
            Creates a new SelectBone.

            :param defaultValue: key(s) which will be checked by default
            :param values: dict of key->value pairs from which the user can choose from.
        """
        super().__init__(defaultValue=defaultValue, **kwargs)

        # handle list/tuple as dicts
        if isinstance(values, (list, tuple)):
            values = {i: translate(i) for i in values}

        assert isinstance(values, (dict, OrderedDict)) or callable(values)
        self._values = values

    def __getattribute__(self, item):
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

    def singleValueFromClient(self, value, skel, name, origData):
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
