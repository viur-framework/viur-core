from viur.core.bones.numeric import NumericBone
import time, typing


class SortIndexBone(NumericBone):
    type = "numeric.sortindex"

    def __init__(
        self,
        *,
        defaultValue: typing.Union[int, float] = lambda *args, **kwargs: time.time(),
        descr: str = "SortIndex",
        max: typing.Union[int, float] = pow(2, 30),
        precision: int = 8,
        **kwargs
    ):
        super().__init__(
            defaultValue=defaultValue,
            descr=descr,
            max=max,
            precision=precision,
            **kwargs
        )
