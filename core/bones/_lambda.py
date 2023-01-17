from typing import Union, Callable
from viur.core.bones.raw import RawBone


class LambdaBone(RawBone):
    """
        This bone return  value from a python function or from eval
    """

    type = "raw.lambda"

    def __init__(self, indexed: bool = False, multiple: bool = False, languages: bool = None, readonly: bool = True,
                 code: Union[str, Callable] = None,
                 provide_skel: bool = False,
                 *args, **kwargs):
        """
                Initializes a new LambdaBone.
                :param code
                    The code can be a lamda function:
                        >>> LambdaBone(code=lambda : "Hello "+"World")

                    It can be a function:
                        >>> def test():
                        >>>     return "Hello World"
                        >>> LambdaBone(code=test)

                    It can be a valid eval expression:
                        >>> LambdaBone(code="'Hello'+'World'")
                :param provide_skel With this you can pass the skeleton instance to the function.This only works when
                    code is a function with the parameter __skel__ or with **kwargs.
                    Example:
                        We can access other Bones inside the test function
                        >>> def test(__skel__):
                        >>>     return __skel__.["otherBone"]
                        >>> otherBone=StringBone()
                        >>> LambdaBone(code=test, provide_skel=True)


        """
        assert not multiple
        assert not languages
        assert not indexed
        assert readonly  # Can we trust our User
        super().__init__(*args, **kwargs)
        self.code = code
        self.provide_skel = provide_skel

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        return False

    def unserialize(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> bool:
        if callable(self.code):
            if self.provide_skel:
                tmp_skel = skel.clone()
                tmp_skel[name] = None  # we must remove our bone because of recursion
                skel.accessedValues[name] = self.code(__skel__=tmp_skel)
            else:
                skel.accessedValues[name] = self.code()
            return True
        if isinstance(self.code, str):
            skel.accessedValues[name] = eval(self.code)
            return True

        return False
