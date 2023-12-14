import typing as t
import time
from viur.core.bones.numeric import NumericBone


class SortIndexBone(NumericBone):
    """
    The SortIndexBone class is specifically designed to handle sorting indexes for data elements, which are
    numeric values that determine the order of these elements. It inherits from the NumericBone.

    :param int | float defaultValue: A default value for the bone, which is a function that returns
        the current time by default. This parameter accepts either an integer or a floating-point number.
    :param str descr: A short description of the bone, set to "SortIndex" by default.
    :param int precision: The precision of the numeric value, determining the number of decimal places allowed.
        The default value is 8.
    :param dict kwargs: Additional keyword arguments that can be passed to the parent NumericBone class.
    """
    type = "numeric.sortindex"

    def __init__(
        self,
        *,
        defaultValue: int | float = lambda *args, **kwargs: time.time(),
        descr: str = "SortIndex",
        precision: int = 8,
        **kwargs
    ):
        super().__init__(
            defaultValue=defaultValue,
            descr=descr,
            precision=precision,
            **kwargs
        )
