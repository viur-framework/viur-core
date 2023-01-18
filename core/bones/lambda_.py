import inspect
from datetime import timedelta
from typing import Callable
from viur.core.bones.base import BaseBone
from viur.core import utils


class LambdaBone(BaseBone):
    """
        This bone return  value from a python function
    """

    type = "lambda"

    def __init__(self, indexed: bool = False, multiple: bool = False, languages: bool = None, readonly: bool = True,
                 evaluate: Callable = None,
                 threshold: int = 0,
                 *args, **kwargs):
        """
                Initializes a new LambdaBone.
                :param evaluate
                    The code can be a lamda function:
                        >>> LambdaBone(evaluate=lambda __skel__ : "Hello "+"World")

                    It can be a function:
                        >>> def test(__skel__):
                        >>>     return "Hello World"
                        >>> LambdaBone(evaluate=test)
                :param threshold The time in minutes before the value is unvalid


        """
        assert not multiple
        assert not languages
        assert not indexed
        assert readonly, "Cannot set readonly to LambdaBone"
        assert callable(evaluate), "'evaluate' must be a callable."
        super().__init__(*args, **kwargs)
        self.evaluate = evaluate
        self.threshold = threshold
        self._accept_skel_arg = "skel" in inspect.signature(evaluate).parameters

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        if name in skel.accessedValues:
            # Ensure this bone is NOT indexed!
            skel.dbEntity.exclude_from_indexes.add(name)

            return True

        return False

    def unserialize(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> bool:
        if data := skel.dbEntity.get(name):
            if data["valid_until"] > utils.utcNow():
                # value is still valid
                skel.accessedValues[name] = data["value"]  # save only the value
                return True

        if data := self._evaluate(skel, name):
            skel.accessedValues[name] = data
            skel.dbEntity[name] = {"value": data, "valid_until": utils.utcNow() + timedelta(seconds=self.threshold)}

        return True

    def _evaluate(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str):
        if not self._accept_skel_arg:
            return self.evaluate()  # call without any arguments

        skel = skel.clone()
        skel[name] = None  # we must remove our bone because of recursion
        return self.evaluate(skel=skel)

    def refresh(self, skel: 'viur.core.skeleton.SkeletonInstance', boneName: str) -> None:
        """
            Refresh the output of the self.evaluate function
        """

        skel.dbEntity[boneName] = {"value": self._evaluate(skel, boneName),
                                   "valid_until": utils.utcNow() + timedelta(seconds=self.threshold)}
        skel.accessedValues[boneName] = skel.dbEntity[boneName]["value"]
