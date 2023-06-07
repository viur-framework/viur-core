from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity
from viur.core import db, conf
from typing import Dict, List, Optional, Any, Union


class BooleanBone(BaseBone):
    type = "bool"

    def __init__(
        self,
        *,
        defaultValue: Union[
            bool,
            List[bool],
            Dict[str, Union[List[bool], bool]],
        ] = None,
        **kwargs
    ):
        if defaultValue is None:
            if kwargs.get("multiple") or kwargs.get("languages"):
                # BaseBone's __init__ will choose an empty container for this
                defaultValue = None
            else:
                # We have a single bone which is False
                defaultValue = False
        else:
            # We have given an explicit defaultValue and maybe a complex structure
            if not (kwargs.get("multiple") or kwargs.get("languages")) and not isinstance(defaultValue, bool):
                raise TypeError("Only 'True' or 'False' can be provided as BooleanBone defaultValue")
            # TODO: missing validation for complex types, but in other bones too

        super().__init__(defaultValue=defaultValue, **kwargs)

    def singleValueFromClient(self, value, skel: 'viur.core.skeleton.SkeletonInstance', name: str, origData):
        return str(value).strip().lower() in conf["viur.bone.boolean.str2true"], None

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
            skel[boneName] = str(skel[boneName]).strip().lower() in conf["viur.bone.boolean.str2true"]

    def buildDBFilter(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: Dict,
        prefix: Optional[str] = None
    ) -> db.Query:
        if name in rawFilter:
            val = str(rawFilter[name]).strip().lower() in conf["viur.bone.boolean.str2true"]
            return super().buildDBFilter(name, skel, dbFilter, {name: val}, prefix=prefix)

        return dbFilter
