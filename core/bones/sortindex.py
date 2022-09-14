from viur.core.bones.numeric import NumericBone
import time, typing


class SortIndexBone(NumericBone):
    type = "numeric.sortindex"

    def __init__(
        self,
        *,
        defaultValue: typing.Union[int, float] = lambda *args, **kwargs: time.time(),
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
