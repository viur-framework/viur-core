import logging
from datetime import datetime, timedelta
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
        assert readonly  # Can we trust our User
        super().__init__(*args, **kwargs)
        self.evaluate = evaluate
        self.threshold = threshold

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        if name in skel.accessedValues:
            skel.dbEntity[name] = skel.accessedValues[name]

            # Ensure this bone is NOT indexed!
            skel.dbEntity.exclude_from_indexes.add(name)

            return True

        return False

    def unserialize(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> bool:
        res = {}
        if data := skel.dbEntity.get(name):
            if data["valid_until"] > utils.utcNow():
                res = data
            else:
                if callable(self.evaluate):
                    res["value"] = self.evaluate_function(skel, name)
                    res["valid_until"] = utils.utcNow() + timedelta(minutes=self.threshold)

            skel.accessedValues[name] = res

            return True
        else:
            if callable(self.evaluate):
                res["value"] = self.evaluate_function(skel, name)
                res["valid_until"] = utils.utcNow() + timedelta(seconds=self.threshold)
                skel.accessedValues[name] = res
                return True
        return False

    def evaluate_function(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str):
        tmp_skel = skel.clone()
        tmp_skel[name] = None  # we must remove our bone because of recursion
        return self.evaluate(__skel__=tmp_skel)

    def refresh(self, skel: 'viur.core.skeleton.SkeletonInstance', boneName: str) -> None:
        """
            Refresh the output of the self.evaluate fuction
        """
        skel[boneName] = {"value": self.evaluate_function(skel, boneName),
                          "valid_until": utils.utcNow() + timedelta(seconds=self.threshold)}
