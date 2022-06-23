from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core import db
from typing import Dict, List, Optional, Union, Any
import logging


class BooleanBone(BaseBone):
    type = "bool"
    trueStrs = [str(True), "1", "yes"]

    def __init__(
        self,
        *,
        defaultValue: bool = False,
        **kwargs
    ):
        if defaultValue not in (True, False):
            raise ValueError("Only 'True' or 'False' can be provided as BooleanBone defaultValue")

        super().__init__(defaultValue=defaultValue, **kwargs)

    def singleValueFromClient(self, value, skel: 'viur.core.skeleton.SkeletonInstance', name: str, origData):
        if str(value) in self.trueStrs:
            return True, None
        else:
            return False, None

    def getEmptyValue(self):
        return False

    def isEmpty(self, rawValue: Any):
        if rawValue is self.getEmptyValue():
            return True
        return not bool(rawValue)

    def refresh(self, skel: 'viur.core.skeleton.SkeletonInstance', boneName: str) -> None:
        """
            Inverse of serialize. Evaluates whats
            read from the datastore and populates
            this bone accordingly.

            :param name: The property-name this bone has in its Skeleton (not the description!)
        """
        if not isinstance(skel[boneName], bool):
            val = skel[boneName]
            if str(val) in self.trueStrs:
                skel[boneName] = True
            else:
                skel[boneName] = False

    def buildDBFilter(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: Dict,
        prefix: Optional[str] = None
    ) -> db.Query:
        if name in rawFilter:
            val = rawFilter[name]
            if str(val) in self.trueStrs:
                val = True
            else:
                val = False

            return super().buildDBFilter(name, skel, dbFilter, {name: val}, prefix=prefix)

        return dbFilter
