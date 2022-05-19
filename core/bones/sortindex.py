from viur.core.bones.numeric import NumericBone
import time


class SortIndexBone(NumericBone):
	type = "numeric.sortindex"

	def __init__(
		self,
	    *,
		defaultValue=lambda: time.time(),
		descr="SortIndex",
		max=pow(2, 30),
		precision=8,
		**kwargs
	):
		super().__init__(
			defaultValue=defaultValue,
			descr=descr,
			max=max,
			precision=precision,
			**kwargs
		)
