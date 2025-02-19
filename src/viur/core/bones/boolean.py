import typing as t

from viur.core import conf, db, utils
from viur.core.bones.base import BaseBone

DEFAULT_VALUE_T: t.TypeAlias = bool | None | list[bool] | dict[str, list[bool] | bool]


class BooleanBone(BaseBone):
    """
    Represents a boolean data type, which can have two possible values: `True` or `False`.
    It also allows for `None` to specify the "not yet set"-state.
    BooleanBones cannot be defined as `multiple=True`.

    :param defaultValue: The default value of the `BooleanBone` instance. Defaults to `None` (unset).
    :raises ValueError: If the `defaultValue` is not either a boolean value (`True` or `False`) or `None`.
    """
    type = "bool"

    def __init__(
        self,
        *,
        defaultValue: DEFAULT_VALUE_T | t.Callable[[t.Self, "SkeletonInstance"], DEFAULT_VALUE_T] = None,
        **kwargs
    ):
        if defaultValue is not None:
            # We have given an explicit defaultValue and maybe a complex structure
            if not kwargs.get("languages") and not (isinstance(defaultValue, bool) or callable(defaultValue)):
                raise TypeError("Only True, False, None or callable can be provided as BooleanBone defaultValue")
            # TODO: missing validation for complex types, but in other bones too

        super().__init__(defaultValue=defaultValue, **kwargs)

        # Disallow creation of BooleanBone(multiple=True)
        if self.multiple:
            raise ValueError("BooleanBone cannot be multiple")

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        return utils.parse.bool(value, conf.bone_boolean_str2true), None

    def getEmptyValue(self):
        """
        Returns the empty value of the `BooleanBone` class, which is `False`.

        :return: The empty value of the `BooleanBone` class (`False`).
        :rtype: bool
        """
        return False

    def isEmpty(self, value: t.Any):
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

    def refresh(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> None:
        """
            Inverse of serialize. Evaluates whats
            read from the datastore and populates
            this bone accordingly.

            :param name: The property-name this bone has in its Skeleton (not the description!)
        """
        if self.languages:
            for lang in self.languages:
                skel[name][lang] = utils.parse.bool(skel[name][lang], conf.bone_boolean_str2true) \
                    if lang in skel[name] else self.getDefaultValue(skel)
        elif skel[name] != self.getEmptyValue():
            # Enforce a boolean if the bone is not empty (Maybe the empty value is explicit set to None).
            # So in this case we keep the empty value (e.g. the None) as is.
            skel[name] = utils.parse.bool(skel[name], conf.bone_boolean_str2true)

    def setBoneValue(
        self,
        skel: 'SkeletonInstance',
        boneName: str,
        value: t.Any,
        append: bool,
        language: None | str = None
    ) -> bool:
        """
        Sets the value of the bone to the provided 'value'.
        Sanity checks are performed; if the value is invalid, the bone value will revert to its original
        (default) value and the function will return False.

        :param skel: Dictionary with the current values from the skeleton the bone belongs to
        :param boneName: The name of the bone that should be modified
        :param value: The value that should be assigned. Its type depends on the type of the bone
        :param append: If True, the given value will be appended to the existing bone values instead of
            replacing them. Only supported on bones with multiple=True
        :param language: Optional, the language of the value if the bone is language-aware
        :return: A boolean indicating whether the operation succeeded or not
        :rtype: bool
        """
        if append:
            raise ValueError(f"append is not possible on {self.type} bones")

        if language:
            if not self.languages or language not in self.languages:
                return False

            skel[boneName][language] = utils.parse.bool(value)
        else:
            skel[boneName] = utils.parse.bool(value)

        return True

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        """
            Serializes a single value of the bone for storage in the database.

            Derived bone classes should overwrite this method to implement their own logic for serializing single
            values.
            The serialized value should be suitable for storage in the database.
        """
        if value == self.getEmptyValue():
            # Keep the bones empty, maybe the empty value is explicit set to None
            return value
        return utils.parse.bool(value, conf.bone_boolean_str2true)

    def buildDBFilter(
        self,
        name: str,
        skel: 'viur.core.skeleton.SkeletonInstance',
        dbFilter: db.Query,
        rawFilter: dict,
        prefix: t.Optional[str] = None
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
            val = utils.parse.bool(rawFilter[name], conf.bone_boolean_str2true)
            return super().buildDBFilter(name, skel, dbFilter, {name: val}, prefix=prefix)

        return dbFilter
