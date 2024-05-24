import logging
import numbers
import sys
import typing as t
import warnings

from viur.core import db
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity

if t.TYPE_CHECKING:
    from viur.core.skeleton import SkeletonInstance

# Constants for Mne (MIN/MAX-never-exceed)
MIN = -(sys.maxsize - 1)
"""Constant for the minimum possible value in the system"""
MAX = sys.maxsize
"""Constant for the maximum possible value in the system"""


class NumericBone(BaseBone):
    """
        A bone for storing numeric values, either integers or floats.
        For floats, the precision can be specified in decimal-places.

        :param precision: How may decimal places should be saved. Zero casts the value to int instead of
            float.
        :param min: Minimum accepted value (including).
        :param max: Maximum accepted value (including).
    """
    type = "numeric"

    def __init__(
        self,
        *,
        max: int | float = MAX,
        min: int | float = MIN,
        mode=None,  # deprecated!
        precision: int = 0,
        **kwargs
    ):
        """
            Initializes a new NumericBone.
        """
        super().__init__(**kwargs)

        if mode:
            logging.warning("mode-parameter to NumericBone is deprecated")
            warnings.warn(
                "mode-parameter to NumericBone is deprecated", DeprecationWarning
            )

        if not precision and mode == "float":
            logging.warning("mode='float' is deprecated, use precision=8 for same behavior")
            warnings.warn(
                "mode='float' is deprecated, use precision=8 for same behavior", DeprecationWarning
            )
            precision = 8

        self.precision = precision
        self.min = min
        self.max = max

    def __setattr__(self, key, value):
        """
        Sets the attribute with the specified key to the given value.

        This method is overridden in the NumericBone class to handle the special case of setting
        the 'multiple' attribute to True while the bone is of type float. In this case, an
        AssertionError is raised to prevent creating a multiple float bone.

        :param key: The name of the attribute to be set.
        :param value: The value to set the attribute to.
        :raises AssertionError: If the 'multiple' attribute is set to True for a float bone.
        """
        if key in ("min", "max"):
            if value < MIN or value > MAX:
                raise ValueError(f"{key} can only be set to something between {MIN} and {MAX}")

        return super().__setattr__(key, value)

    def isInvalid(self, value):
        """
        This method checks if a given value is invalid (e.g., NaN) for the NumericBone instance.

        :param value: The value to be checked for validity.
        :return: Returns a string "NaN not allowed" if the value is invalid (NaN), otherwise None.
        """
        if value != value:  # NaN
            return "NaN not allowed"

    def getEmptyValue(self):
        """
        This method returns an empty value depending on the precision attribute of the NumericBone
        instance.

        :return: Returns 0 for integers (when precision is 0) or 0.0 for floating-point numbers (when
            precision is non-zero).
        """
        if self.precision:
            return 0.0
        else:
            return 0

    def isEmpty(self, value: t.Any):
        """
        This method checks if a given raw value is considered empty for the NumericBone instance.
        It attempts to convert the raw value into a valid numeric value (integer or floating-point
        number), depending on the precision attribute of the NumericBone instance.

        :param value: The raw value to be checked for emptiness.
        :return: Returns True if the raw value is considered empty, otherwise False.
        """
        if isinstance(value, str) and not value:
            return True
        try:
            value = self._convert_to_numeric(value)
        except (ValueError, TypeError):
            return True
        return value == self.getEmptyValue()

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        try:
            value = str(value).replace(",", ".", 1)
        except:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid Value")]
        else:
            if self.precision and (str(value).replace(".", "", 1).replace("-", "", 1).isdigit()) and float(
                    value) >= self.min and float(value) <= self.max:
                value = round(float(value), self.precision)
            elif not self.precision and (str(value).replace("-", "", 1).isdigit()) and int(
                    value) >= self.min and int(value) <= self.max:
                value = int(value)
            else:
                return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Invalid Value")]
        err = self.isInvalid(value)
        if err:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]
        return value, None

    def buildDBFilter(
        self,
        name: str,
        skel: "SkeletonInstance",
        dbFilter: db.Query,
        rawFilter: dict,
        prefix: t.Optional[str] = None
    ) -> db.Query:
        updatedFilter = {}

        for parmKey, paramValue in rawFilter.items():
            if parmKey.startswith(name):
                if parmKey != name and not parmKey.startswith(name + "$"):
                    # It's just another bone which name start's with our's
                    continue
                try:
                    if not self.precision:
                        paramValue = int(paramValue)
                    else:
                        paramValue = float(paramValue)
                except ValueError:
                    # The value we should filter by is garbage, cancel this query
                    logging.warning(f"Invalid filtering! Unparsable int/float supplied to NumericBone {name}")
                    raise RuntimeError()
                updatedFilter[parmKey] = paramValue

        return super().buildDBFilter(name, skel, dbFilter, updatedFilter, prefix)

    def getSearchTags(self, skel: "SkeletonInstance", name: str) -> set[str]:
        """
        This method generates a set of search tags based on the numeric values stored in the NumericBone
        instance. It iterates through the bone values and adds the string representation of each value
        to the result set.

        :param skel: The skeleton instance containing the bone.
        :param name: The name of the bone.
        :return: Returns a set of search tags as strings.
        """
        result = set()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            result.add(str(value))
        return result

    def _convert_to_numeric(self, value: t.Any) -> int | float:
        """Convert a value to an int or float considering the precision.

        If the value is not convertable an exception will be raised."""
        if isinstance(value, str):
            value = value.replace(",", ".", 1)
        if self.precision:
            return float(value)
        else:
            # First convert to float then to int to support "42.5" (str)
            return int(float(value))

    def refresh(self, skel: "SkeletonInstance", boneName: str) -> None:
        """Ensure the value is numeric or None.

        This ensures numeric values, for example after changing
        a bone from StringBone to a NumericBone.
        """
        super().refresh(skel, boneName)

        def refresh_single_value(value: t.Any) -> float | int:
            if value == "":
                return self.getEmptyValue()
            elif not isinstance(value, (int, float, type(None))):
                return self._convert_to_numeric(value)
            return value

        # TODO: duplicate code, this is the same iteration logic as in StringBone
        new_value = {}
        for _, lang, value in self.iter_bone_value(skel, boneName):
            new_value.setdefault(lang, []).append(refresh_single_value(value))

        if not self.multiple:
            # take the first one
            new_value = {lang: values[0] for lang, values in new_value.items() if values}

        if self.languages:
            skel[boneName] = new_value
        elif not self.languages:
            # just the value(s) with None language
            skel[boneName] = new_value.get(None, [] if self.multiple else self.getEmptyValue())

    def iter_bone_value(
        self, skel: "SkeletonInstance", name: str
    ) -> t.Iterator[tuple[t.Optional[int], t.Optional[str], t.Any]]:
        value = skel[name]
        if not value and isinstance(value, numbers.Number):
            # 0 and 0.0 are falsy, but can be valid numeric values and should be kept
            yield None, None, value
        yield from super().iter_bone_value(skel, name)

    def structure(self) -> dict:
        return super().structure() | {
            "min": self.min,
            "max": self.max,
            "precision": self.precision,
        }
