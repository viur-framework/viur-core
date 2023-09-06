from typing import Any, Dict, List, Optional, Union

from viur.core import conf, db
from viur.core.bones.base import BaseBone
from viur.core.utils import parse_bool


class BooleanBone(BaseBone):
    """
    Represents a boolean data type, which can have two possible values: `True` or `False`.
    BooleanBones cannot be defined as `multiple=True`.

    :param defaultValue: The default value of the `BooleanBone` instance. Defaults to `False`.
    :type defaultValue: bool
    :raises ValueError: If the `defaultValue` is not a boolean value (`True` or `False`).
    """
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

        # Disallow creation of BooleanBone(multiple=True)
        if self.multiple:
            raise ValueError("BooleanBone cannot be multiple")

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        return parse_bool(value, conf["viur.bone.boolean.str2true"]), None

    def getEmptyValue(self):
        """
        Returns the empty value of the `BooleanBone` class, which is `False`.

        :return: The empty value of the `BooleanBone` class (`False`).
        :rtype: bool
        """
        return False

    def isEmpty(self, value: Any):
        """
        Checks if the given boolean value is empty.

        :param value: The boolean value to be checked.
        :return: `True` if the boolean value is empty (i.e., equal to the empty value of the `BooleanBone` class), \
            `False` otherwise.
        :rtype: bool
        """
        if value is self.getEmptyValue():
            return True
        return not bool(value)

    def refresh(self, skel: 'viur.core.skeleton.SkeletonInstance', boneName: str) -> None:
        """
            Inverse of serialize. Evaluates whats
            read from the datastore and populates
            this bone accordingly.

            :param name: The property-name this bone has in its Skeleton (not the description!)
        """
        if not isinstance(skel[boneName], bool):
            skel[boneName] = parse_bool(skel[boneName], conf["viur.bone.boolean.str2true"])

    def buildDBFilter(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: Dict,
        prefix: Optional[str] = None
    ) -> db.Query:
        """
        Builds a database filter based on the boolean value.

        :param name: The name of the `BooleanBone` instance.
        :param skel: The `SkeletonInstance` object representing the data of the current entity.
        :param dbFilter: The `Query` object representing the current database filter.
        :param rawFilter: The dictionary representing the raw filter data received from the client.
        :param prefix: A prefix to be added to the property name in the database filter.
        :return: The updated `Query` object representing the updated database filter.
        :rtype: google.cloud.ndb.query.Query
        """
        if name in rawFilter:
            val = parse_bool(rawFilter[name], conf["viur.bone.boolean.str2true"])
            return super().buildDBFilter(name, skel, dbFilter, {name: val}, prefix=prefix)

        return dbFilter
